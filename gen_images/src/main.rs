use clap::Parser;
use flate2::{Compression, bufread::GzDecoder, write::GzEncoder};
use regex::Regex;
use serde::Deserialize;
use sha_crypt::{Sha512Params, sha512_simple};
use std::{
    collections::HashMap,
    fs::File,
    io::{BufReader, BufWriter, Seek, SeekFrom, Write, copy},
    path::{Path, PathBuf},
    process::{Command, ExitStatus, Stdio},
    sync::LazyLock,
};
use tempfile::{NamedTempFile, TempDir};

/// Generates one or more Debian ISO images with a preseed configuration. The preseed images are
/// saved to the ./artifacts/ directory, while the original unmodified images are saved to the
/// ./cache/ directory.
/// Project home page: https://app.radicle.xyz/nodes/iris.radicle.xyz/rad:zoBPQV6X2FH296n9gQxJr6suvSSi
#[derive(Debug, Parser)]
#[command(author, version, about, long_about)]
struct Args {
    /// Enable verbose output
    #[arg(short, long)]
    verbose: bool,
    /// Enable debugging
    #[arg(short, long)]
    debug: bool,
}

fn main() -> anyhow::Result<()> {
    let args = Args::parse();

    let output_dir = Path::new("/artifacts");
    let cache_dir = Path::new("/cache");
    let tmp_dir = args.debug.then(|| Path::new("/tmp"));

    {
        let cache_tag = cache_dir.join("CACHEDIR.TAG");
        let mut cache_tag =
            File::create(&cache_tag).map_err(|e| Error::FileCreate(cache_tag.to_path_buf(), e))?;
        writeln!(cache_tag, "Signature: 8a477f597d28d172789f06886806bc55")?;
    }

    let stdin = std::io::stdin();
    let payload: Payload =
        serde_json::from_reader(BufReader::new(stdin.lock())).map_err(|e| Error::Payload(e))?;
    for spec in payload.iter_specs() {
        build_image(&spec, output_dir, cache_dir, tmp_dir, args.verbose)?;
    }

    Ok(())
}

#[derive(Debug, thiserror::Error)]
enum Error {
    #[error("Could not create the file {}", .0.display())]
    FileCreate(PathBuf, #[source] std::io::Error),
    #[error("Could not open the file {}", .0.display())]
    FileOpen(PathBuf, #[source] std::io::Error),
    #[error("Could not write to a file")]
    FileWrite(#[source] std::io::Error),
    #[error("Could not read from a file")]
    FileRead(#[source] std::io::Error),
    #[error("Could not seek on a file")]
    FileSeek(#[source] std::io::Error),
    #[error("Could not copy file contents from one to another")]
    CopyFileContents(#[source] std::io::Error),
    #[error("Could not gzip-encode a file")]
    GzEncoding(#[source] std::io::Error),
    #[error("Executing process '{0}'")]
    ExecuteProcess(&'static str, #[source] std::io::Error),
    #[error("Process '{0}' exited with status {1}")]
    ProcessExitStatus(&'static str, ExitStatus),
    #[error("Could not decode the payload from stdin")]
    Payload(#[source] serde_json::Error),
    #[error("Could not create a temporary directory with prefix '{0}'")]
    Tempdir(&'static str, #[source] std::io::Error),
    #[error("Could not create a temporary file with prefix '{0}'")]
    Tempfile(&'static str, #[source] std::io::Error),
    #[error("Could not persist a temporary file")]
    KeepTempfile(#[from] tempfile::PersistError),
    #[error(transparent)]
    FromUtf8(#[from] std::string::FromUtf8Error),
    #[error("Could not parse '{0}' as integer")]
    ParseInt(String, #[source] std::num::ParseIntError),
    #[error("Cannot find the EFI partition in the disk image")]
    EfiPartition,
    #[error(transparent)]
    HttpGetRequest(#[from] ureq::Error),
}

/// Define all parameters for a particular Debian installer image.
#[derive(Debug)]
struct ImageSpec<'a> {
    host_name: &'a str,
    arch: Arch,
    boot_device: &'a str,
    root_password: &'a Sha512Crypted,
    ansible_vault_password: &'a str,
    git_author_email: &'a str,
    git_author_ssh_pub: &'a str,
    bootstrap_repo: &'a str,
    bootstrap_branch: &'a str,
    bootstrap_dest: &'a str,
    debian_mirror: &'a str,
    debian_version: &'a str,
    install_nonfree_firmware: bool,
    timezone: &'a str,
    domain: Option<&'a str>,
    ansible_home: &'a str,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
#[serde(rename_all = "lowercase")]
enum Arch {
    Amd64,
    I386,
    Arm64,
}

impl Arch {
    fn to_grub(self) -> &'static str {
        match self {
            Arch::Amd64 => "amd",
            Arch::I386 => "386",
            Arch::Arm64 => "a64",
        }
    }
}

impl std::fmt::Display for Arch {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Arch::Amd64 => write!(f, "amd64"),
            Arch::I386 => write!(f, "i386"),
            Arch::Arm64 => write!(f, "arm64"),
        }
    }
}

#[derive(Debug, Deserialize)]
struct HostData {
    host_name: String,
    arch: Arch,
    boot_device: String,
}

#[derive(Debug, Deserialize)]
struct Options {
    bootstrap_repo: String,
    bootstrap_branch: String,
    bootstrap_dest: String,
    debian_mirror: String,
    debian_version: String,
    install_nonfree_firmware: bool,
    timezone: String,
    domain: Option<String>,
    ansible_home: String,
}

impl Default for Options {
    fn default() -> Self {
        Options {
            bootstrap_repo: "https://iris.radicle.xyz/zoBPQV6X2FH296n9gQxJr6suvSSi.git".into(),
            bootstrap_branch: "main".into(),
            bootstrap_dest: "/var/lib/ansible/repo".into(),
            debian_mirror: "debian.ethz.ch".into(),
            debian_version: "13.3.0".into(),
            install_nonfree_firmware: false,
            timezone: "Europe/Zurich".into(),
            domain: None,
            ansible_home: "/var/lib/ansible".into(),
        }
    }
}

#[derive(Debug, thiserror::Error)]
enum CryptError {
    #[error(
        "Expected rounds to be within range {}..={}_u32",
        sha_crypt::ROUNDS_MIN,
        sha_crypt::ROUNDS_MAX
    )]
    Rounds,
    #[error("Error during random number generation")]
    Random,
    #[error("I/O error: {0}")]
    Io(#[source] std::io::Error),
    #[error("UTF-8 conversion error: {0}")]
    FromUtf8(#[source] std::string::FromUtf8Error),
}

impl From<sha_crypt::CryptError> for CryptError {
    fn from(value: sha_crypt::CryptError) -> Self {
        match value {
            sha_crypt::CryptError::RoundsError => Self::Rounds,
            sha_crypt::CryptError::RandomError => Self::Random,
            sha_crypt::CryptError::IoError(error) => Self::Io(error),
            sha_crypt::CryptError::StringError(error) => Self::FromUtf8(error),
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(try_from = "String")]
struct Sha512Crypted(String);

impl TryFrom<String> for Sha512Crypted {
    type Error = CryptError;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        Ok(Self(sha512_simple(&value, &Sha512Params::default())?))
    }
}

impl std::ops::Deref for Sha512Crypted {
    type Target = str;

    fn deref(&self) -> &Self::Target {
        self.0.as_str()
    }
}

#[derive(Debug, Deserialize)]
struct Payload {
    host_data: Vec<HostData>,
    ansible_vault_password: String,
    git_author_email: String,
    git_author_ssh_pub: String,
    root_password: Sha512Crypted,
    #[serde(default)]
    options: Options,
}

impl Payload {
    fn iter_specs<'a>(&'a self) -> impl Iterator<Item = ImageSpec<'a>> {
        self.host_data.iter().map(|hd| ImageSpec {
            host_name: &hd.host_name,
            arch: hd.arch,
            boot_device: &hd.boot_device,
            root_password: &self.root_password,
            ansible_vault_password: &self.ansible_vault_password,
            git_author_email: &self.git_author_email,
            git_author_ssh_pub: &self.git_author_ssh_pub,
            bootstrap_repo: &self.options.bootstrap_repo,
            bootstrap_branch: &self.options.bootstrap_branch,
            bootstrap_dest: &self.options.bootstrap_dest,
            debian_mirror: &self.options.debian_mirror,
            debian_version: &self.options.debian_version,
            install_nonfree_firmware: self.options.install_nonfree_firmware,
            timezone: &self.options.timezone,
            domain: self.options.domain.as_deref(),
            ansible_home: &self.options.ansible_home,
        })
    }
}

/// Download, extract, modify, and rebuild a Debian installer image.
fn build_image(
    spec: &ImageSpec,
    output: &Path,
    cache: &Path,
    temp: Option<&Path>,
    verbose: bool,
) -> Result<(), Error> {
    let image_staging_dir = temp
        .map(|tp| TempDir::with_prefix_in("staging", tp))
        .unwrap_or_else(|| TempDir::with_prefix("staging"))
        .map_err(|e| Error::Tempdir("staging", e))?;
    let orig_image = download_image(cache, &spec.debian_version, spec.arch, verbose)?;
    unpack_image(&orig_image, image_staging_dir.path())?;
    template_grub(image_staging_dir.path(), spec)?;
    template_post_install(image_staging_dir.path(), spec)?;
    {
        let preseed_staging_dir = temp
            .map(|tp| TempDir::with_prefix_in("preseed", tp))
            .unwrap_or_else(|| TempDir::with_prefix("preseed"))
            .map_err(|e| Error::Tempdir("preseed", e))?;
        template_preseed(preseed_staging_dir.path(), spec)?;
        bake_preseed(
            preseed_staging_dir.path(),
            image_staging_dir.path(),
            spec,
            temp,
        )?;
        if temp.is_some() {
            println!(
                "Preseed file for {}/{} saved to: {}",
                spec.host_name,
                spec.arch,
                preseed_staging_dir.keep().display()
            );
        }
    }
    update_md5sums(image_staging_dir.path())?;
    repack_image(
        output,
        spec,
        &orig_image,
        image_staging_dir.path(),
        temp,
        verbose,
    )?;

    if temp.is_some() {
        println!(
            "Image staging dir for {}/{} saved to: {}",
            spec.host_name,
            spec.arch,
            image_staging_dir.keep().display()
        );
    }

    Ok(())
}

/// Append the preseed.cfg to the initrd.gz archive in the installer image. This is an in-place operation that modifies the initrd.gz archive.
fn bake_preseed(
    preseed_staging_dir: &Path,
    image_staging_dir: &Path,
    spec: &ImageSpec<'_>,
    temp: Option<&Path>,
) -> Result<PathBuf, Error> {
    let initrd_path = image_staging_dir.join(format!("install.{}/initrd.gz", spec.arch.to_grub()));
    let mut initrd_decompressed = temp
        .map(|tp| NamedTempFile::with_prefix_in("initrd", tp))
        .unwrap_or_else(|| NamedTempFile::with_prefix("initrd"))
        .map_err(|e| Error::Tempfile("initrd", e))?;

    // Decompress the initrd.gz file to the temporary location.
    {
        let initrd =
            File::open(&initrd_path).map_err(|e| Error::FileOpen(initrd_path.to_path_buf(), e))?;
        copy(
            &mut GzDecoder::new(BufReader::new(initrd)),
            &mut initrd_decompressed,
        )
        .map_err(|e| Error::CopyFileContents(e))?;
    }

    // Append the preseed.cfg file into the initrd archive.
    {
        let mut proc = Command::new("cpio")
            .args(&[
                "-H",
                "newc",
                "-o",
                "-A",
                "--reproducible",
                "-F",
                &initrd_decompressed.path().to_string_lossy(),
            ])
            .current_dir(preseed_staging_dir)
            .stdin(Stdio::piped())
            .spawn()
            .map_err(|e| Error::ExecuteProcess("cpio", e))?;

        if let Some(mut stdin) = proc.stdin.take() {
            writeln!(stdin, "preseed.cfg").map_err(Error::FileWrite)?;
        }

        let status = proc.wait().map_err(|e| Error::ExecuteProcess("cpio", e))?;

        if !status.success() {
            return Err(Error::ProcessExitStatus("cpio", status));
        }
    }

    // Repack the initrd archive.
    {
        initrd_decompressed
            .seek(SeekFrom::Start(0))
            .map_err(Error::FileSeek)?;
        let initrd = File::create(&initrd_path)
            .map_err(|e| Error::FileCreate(initrd_path.to_path_buf(), e))?;
        let mut encoder = GzEncoder::new(initrd, Compression::default());
        copy(&mut initrd_decompressed, &mut encoder).map_err(|e| Error::CopyFileContents(e))?;
        encoder.finish().map_err(|e| Error::GzEncoding(e))?;
    }

    if temp.is_some() {
        println!(
            "Decompressed and modified Initrd for {}/{} saved to: {}",
            spec.host_name,
            spec.arch,
            initrd_decompressed.keep()?.1.display()
        );
    }

    Ok(initrd_path)
}

/// Rebuild the Debian ISO installer image from an image spec and staging directory.
fn repack_image(
    output: &Path,
    spec: &ImageSpec<'_>,
    orig_image: &Path,
    image_staging_dir: &Path,
    temp: Option<&Path>,
    verbose: bool,
) -> Result<(), Error> {
    let volume_id = format!("{}_{}", &spec.host_name, spec.arch).replace(".", "_");
    let dest = output.join(format!("{}-{}.iso", &spec.host_name, &spec.arch));
    let boot_partition = temp
        .map(|tp| NamedTempFile::with_prefix_in("boot_partition", tp))
        .unwrap_or_else(|| NamedTempFile::with_prefix("boot_partition"))
        .map_err(|e| Error::Tempfile("boot_partition", e))?;
    match spec.arch {
        Arch::Amd64 | Arch::I386 => {
            dd(orig_image, boot_partition.path(), 0, 1, 432)?;
            xorriso(
                &dest,
                &volume_id,
                &[
                    "-isohybrid-mbr",
                    &boot_partition.path().to_string_lossy(),
                    "-b",
                    "isolinux/isolinux.bin",
                    "-c",
                    "isolinux/boot.cat",
                    "-boot-load-size",
                    "4",
                    "-boot-info-table",
                    "-no-emul-boot",
                    "-eltorito-alt-boot",
                    "-e",
                    "boot/grub/efi.img",
                    "-no-emul-boot",
                    "-isohybrid-gpt-basdat",
                    "-isohybrid-apm-hfsplus",
                    &image_staging_dir.to_string_lossy(),
                ],
                verbose,
            )?;
        }
        Arch::Arm64 => {
            let (start_block, block_count) = efi_partition(orig_image)?;
            dd(
                orig_image,
                boot_partition.path(),
                start_block,
                512,
                block_count,
            )?;
            xorriso(
                &dest,
                &volume_id,
                &[
                    "-e",
                    "boot/grub/efi.img",
                    "-no-emul-boot",
                    "-append_partition",
                    "2",
                    "0xef",
                    &boot_partition.path().to_string_lossy(),
                    "-partition_cyl_align",
                    "all",
                    &image_staging_dir.to_string_lossy(),
                ],
                verbose,
            )?;
        }
    }

    if temp.is_some() {
        println!(
            "Extracted EFI/MBR partition for {}/{} saved to: {}",
            spec.host_name,
            spec.arch,
            boot_partition.keep()?.1.display()
        );
    }

    Ok(())
}

/// Create an ISO image from arguments using xorriso.
fn xorriso(dest: &Path, volume_id: &str, extra_args: &[&str], verbose: bool) -> Result<(), Error> {
    let dest = dest.to_string_lossy();
    let mut base_args = vec![
        "-r",
        // "-checksum_algorithm_iso",
        // "sha256,sha512",
        "-volid",
        volume_id,
        "-o",
        &dest,
        "-J",
        "-joliet-long",
    ];
    if !verbose {
        base_args.insert(0, "-quiet");
    }

    let status = Command::new("xorrisofs")
        .args([&base_args, extra_args].concat())
        .status()
        .map_err(|e| Error::ExecuteProcess("xorrisofs", e))?;

    if !status.success() {
        return Err(Error::ProcessExitStatus("xorrisofs", status));
    }

    Ok(())
}

/// Copy the contents of a partition, delimited by start_block and block_count, to the destination.
fn dd(
    src: &Path,
    dest: &Path,
    start_block: usize,
    block_size: usize,
    block_count: usize,
) -> Result<(), Error> {
    let status = Command::new("dd")
        .args([
            &format!("if={}", src.display()),
            &format!("of={}", dest.display()),
            &format!("skip={start_block}"),
            &format!("bs={block_size}"),
            &format!("count={block_count}"),
        ])
        .status()
        .map_err(|e| Error::ExecuteProcess("dd", e))?;

    if !status.success() {
        return Err(Error::ProcessExitStatus("dd", status));
    }

    Ok(())
}

/// Retrieve the EFI partition boundary as a tuple of `(start_block, block_count)`. In the standard
/// output of `fdisk -l <ISO-image>`, try to find the EFI partition. Return a tuple of
/// `(start_block, block_count)`. Raise `ValueError` if the EFI partition cannot be found.
fn efi_partition(orig_image: &Path) -> Result<(usize, usize), Error> {
    let output = Command::new("fdisk")
        .args(&["-l", &orig_image.to_string_lossy()])
        .output()
        .map_err(|e| Error::ExecuteProcess("fdisk", e))?;

    if !output.status.success() {
        return Err(Error::ProcessExitStatus("fdisk", output.status));
    }

    let stdout = String::from_utf8(output.stdout)?;
    for line in stdout.lines() {
        if line.contains(".iso2") && line.contains("EFI") {
            let parts = line.split_whitespace().collect::<Vec<_>>();
            if parts.len() >= 4 {
                let start_block: usize = parts[3]
                    .parse()
                    .map_err(|e| Error::ParseInt(parts[3].to_string(), e))?;
                let block_count: usize = parts[4]
                    .parse()
                    .map_err(|e| Error::ParseInt(parts[4].to_string(), e))?;
                return Ok((start_block, block_count));
            }
        }
    }

    Err(Error::EfiPartition)
}

/// Recalculate all files' MD5 hashes inside the installer image.
fn update_md5sums(image_staging_dir: &Path) -> Result<(), Error> {
    let output_path = image_staging_dir.join("md5sum.txt");
    let output_file =
        File::create(&output_path).map_err(|e| Error::FileCreate(output_path.to_path_buf(), e))?;

    let status = Command::new("find")
        .args([".", "-type", "f", "-exec", "md5sum", "{}", ";"])
        .current_dir(image_staging_dir)
        .stdout(Stdio::from(output_file))
        .status()
        .map_err(|e| Error::ExecuteProcess("find", e))?;

    if !status.success() {
        return Err(Error::ProcessExitStatus("find -exec md5sum", status));
    }
    Ok(())
}

fn template_preseed(preseed_staging_dir: &Path, spec: &ImageSpec<'_>) -> Result<PathBuf, Error> {
    let output = preseed_staging_dir.join("preseed.cfg");
    let nonfree = spec.install_nonfree_firmware.to_string();
    let content = render_template(
        Path::new("/src/preseed.cfg.t"),
        &[
            ("hostname", spec.host_name),
            ("domain", spec.domain.unwrap_or_default()),
            ("mirror", spec.debian_mirror),
            ("password", spec.root_password),
            ("timezone", spec.timezone),
            ("nonfree_firmware", &nonfree),
            ("boot_device", spec.boot_device),
        ],
    )?;
    std::fs::write(&output, content).map_err(Error::FileWrite)?;
    Ok(output)
}

static SUBSTITUTION: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"\$?(\$\{[a-zA-Z][_a-zA-Z0-9]*\}|\$\(.*?\)|\$[a-zA-Z][_a-zA-Z0-9]*)"#).unwrap()
});

fn render_template(src: &Path, params: &[(&str, &str)]) -> Result<String, Error> {
    let params: HashMap<_, _> = params.iter().copied().collect();
    let text = std::fs::read_to_string(src).map_err(Error::FileRead)?;
    let result = SUBSTITUTION.replace_all(&text, |caps: &regex::Captures| {
        let full = caps.get(0).unwrap().as_str();
        let inner = caps.get(1).unwrap().as_str();

        // `$$` escape: drop one `$` and emit the placeholder literally. The same applies to bash
        // command substitution strings that look like string substitution but we are not interested
        // in those.
        if full.starts_with("$$") || full.starts_with("$(") {
            return inner.to_string();
        }

        // Extract the key name (strip `${` ... `}` or `$`).
        let key = if inner.starts_with("${") {
            &inner[2..inner.len() - 1]
        } else {
            &inner[1..]
        };

        // Substitute the placeholder ${key} with the lookup value.
        params
            .get(key)
            .map(|v| v.to_string())
            .unwrap_or_else(|| panic!("Unknown placeholder key '{key}'"))
    });

    Ok(result.into_owned())
}

fn template_post_install(image_staging_dir: &Path, spec: &ImageSpec<'_>) -> Result<PathBuf, Error> {
    let output = image_staging_dir.join("post-install.sh");
    let content = render_template(
        Path::new("/src/post-install.sh.t"),
        &[
            ("repo", spec.bootstrap_repo),
            ("branch", spec.bootstrap_branch),
            ("dest", spec.bootstrap_dest),
            ("ansible_home", spec.ansible_home),
            ("vault_password", spec.ansible_vault_password),
            ("email", spec.git_author_email),
            ("ssh_pub", spec.git_author_ssh_pub),
        ],
    )?;
    std::fs::write(&output, content).map_err(Error::FileWrite)?;
    Ok(output)
}

fn template_grub(image_staging_dir: &Path, spec: &ImageSpec<'_>) -> Result<PathBuf, Error> {
    let output = image_staging_dir.join("boot/grub/grub.cfg");
    let content = render_template(
        Path::new("/src/grub.cfg.t"),
        &[("arch_short", spec.arch.to_grub())],
    )?;
    std::fs::write(&output, content).map_err(Error::FileWrite)?;
    Ok(output)
}

/// Download the Debian netinstall ISO file to the local cache.
fn download_image(dest: &Path, version: &str, arch: Arch, verbose: bool) -> Result<PathBuf, Error> {
    let image_url = format!(
        "https://cdimage.debian.org/debian-cd/{version}/{arch}/iso-cd/debian-{version}-{arch}-netinst.iso"
    );
    let dest = dest.join(format!("debian-{version}-{arch}-netinst.iso"));
    if dest.is_file() {
        return Ok(dest);
    }
    if verbose {
        eprintln!("Downloading '{image_url}' to '{}'", dest.display());
    }
    let mut response = ureq::get(&image_url).call()?;
    let dest_file = File::create(&dest).map_err(|e| Error::FileCreate(dest.to_path_buf(), e))?;
    copy(
        &mut response.body_mut().as_reader(),
        &mut BufWriter::new(dest_file),
    )
    .map_err(Error::CopyFileContents)?;
    Ok(dest)
}

/// Unpack the cached ISO image to a directory.
fn unpack_image(src: &Path, dest: &Path) -> Result<PathBuf, Error> {
    let status = Command::new("bsdtar")
        .args(&["-xf", &src.to_string_lossy()])
        .current_dir(dest)
        .status()
        .map_err(|e| Error::ExecuteProcess("bsdtar", e))?;

    if !status.success() {
        return Err(Error::ProcessExitStatus("bsdtar", status));
    }

    Ok(dest.to_path_buf())
}
