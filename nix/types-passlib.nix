{buildPythonPackage, fetchPypi, lib}:

buildPythonPackage rec {
    pname = "types-passlib";
    version = "1.7.7.20260211";
    format = "setuptools";

    src = fetchPypi {
        pname = "types_passlib";
        inherit version;
        hash = "sha256-r3Ov/+HOlMlcf2ByvSYVcsKYRd50/f+jomX8djS8oFY=";
    };

    propagatedBuildInputs = [];

    # Module doesn't have tests
    doCheck = false;

    pythonImportsCheck = [ "passlib-stubs" ];

    meta = {
        description = "Typing stubs for passlib";
        homepage = "https://github.com/python/typeshed";
        license = lib.licenses.asl20;
    };
}
