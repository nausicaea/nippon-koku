#!/bin/sh

set -e

echo "START POST INSTALL"

ANSIBLE_HOME="${ansible_home}"
ANSIBLE_ETCDIR="/etc/ansible"
ANSIBLE_CFG="$$ANSIBLE_ETCDIR/ansible.cfg"
ANSIBLE_VAULT_PASSWORD="${vault_password}"
ANSIBLE_VAULT_PW_FILE="$$ANSIBLE_HOME/vault_password"
BOOTSTRAP_REPO="${repo}"
BOOTSTRAP_BRANCH="${branch}"
BOOTSTRAP_DEST="${dest}"
GIT_SYSTEM_GITCONFIG="/etc/gitconfig"
GIT_ALLOWED_SIGNERS_FILE="/etc/git/allowed_signers"
GIT_AUTHOR_EMAIL="${email}"
GIT_AUTHOR_SSH_PUB="${ssh_pub}"

echo "PI: Stage 1"
if [ ! -e /dev/shm ]; then
    mkdir -vp /dev/shm
fi

exit_cleanup() {
    if [ -e /dev/shm ]; then
        rmdir -v /dev/shm
    fi
}
trap exit_cleanup EXIT

mkdir -vp "$$ANSIBLE_ETCDIR" "$$ANSIBLE_HOME" $$(dirname "$$GIT_ALLOWED_SIGNERS_FILE")

cat <<EOF > "$$ANSIBLE_CFG"
[defaults]
home = $$ANSIBLE_HOME
interpreter_python = auto_silent
hash_behaviour = merge
pipelining = True
EOF

printf '%s\n' "$$ANSIBLE_VAULT_PASSWORD" > "$$ANSIBLE_VAULT_PW_FILE"

printf '%s namespaces="git" %s\n' "$$GIT_AUTHOR_EMAIL" "$$GIT_AUTHOR_SSH_PUB" > "$$GIT_ALLOWED_SIGNERS_FILE"

cat <<EOF > "$$GIT_SYSTEM_GITCONFIG"
[gpg "ssh"]
    allowedSignersFile = $$GIT_ALLOWED_SIGNERS_FILE
EOF

cat <<EOF > /etc/default/ansible-pull
BOOTSTRAP_BRANCH="$$BOOTSTRAP_BRANCH"
EOF

echo "PI: Stage 2"
export BOOTSTRAP_BRANCH
mkdir -p /var/log/installer
ansible-pull \
    --url="$$BOOTSTRAP_REPO" \
    --checkout="$$BOOTSTRAP_BRANCH" \
    --directory="$$BOOTSTRAP_DEST" \
    --inventory="bootstrap/inventory.yml" \
    --connection="local" \
    --vault-password-file="$$ANSIBLE_VAULT_PW_FILE" \
    --clean \
    "bootstrap/playbook.yml" 2>&1 \
    | tee /var/log/installer/ansible \
    || printf 'ERROR: Ansible run failed with status code %s\n' "$$?"

echo "END POST INSTALL"
