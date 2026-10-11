import pytest

from paxveil.core.parsers import InputError, parse


def test_requirements_exact_markers_hashes_and_unknown():
    result = parse(
        "requirements.txt",
        b"Requests==2.31.0 --hash=sha256:abcd\ncolorama==0.4.6; sys_platform == 'win32'\nurllib3>=2\n",
        platform="linux",
    )
    assert [(dep.name, dep.version, dep.status) for dep in result.dependencies] == [
        ("requests", "2.31.0", "active"),
        ("colorama", "0.4.6", "excluded"),
        ("urllib3", None, "unresolved"),
    ]
    assert result.dependencies[2].specifier == ">=2"


@pytest.mark.parametrize(
    "filename,content",
    [
        ("../../requirements.txt", b"a==1"),
        ("evil.txt", b"a==1"),
        ("requirements.txt", b"not a requirement???"),
        ("requirements.txt", b"\x00"),
        ("requirements.txt", b""),
        ("poetry.lock", b"not toml"),
        ("uv.lock", b"version = 1"),
    ],
)
def test_invalid_files_are_rejected(filename, content):
    with pytest.raises(ValueError):
        parse(filename, content)


def test_uploaded_installer_directives_and_urls_are_not_followed():
    result = parse(
        "requirements.txt",
        b"--index-url https://private.example\n-r secret.txt\nfoo @ https://127.0.0.1/secret.whl\nrequests==2.31.0\n",
    )
    assert result.dependencies[0].status == "unsupported"
    assert result.dependencies[0].version is None
    assert len(result.warnings) >= 4


def test_hash_continuation_and_normalization():
    result = parse(
        "requirements.txt",
        b"my_package==1.2.3 \\\n --hash=sha256:aaaa\nmy-package==1.2.3\n",
    )
    assert len(result.dependencies) == 1
    assert result.dependencies[0].name == "my-package"


def test_poetry_preserves_unknown_roots_and_graph():
    content = b"""[[package]]
name = "requests"
version = "2.31.0"
python-versions = ">=3.7"
[package.dependencies]
urllib3 = ">=1.21.1,<3"
[[package]]
name = "urllib3"
version = "2.0.7"
python-versions = ">=3.7"
"""
    result = parse("poetry.lock", content)
    assert all(dep.direct is None for dep in result.dependencies)
    assert result.edges == [
        {
            "source": "requests==2.31.0",
            "target": "urllib3==2.0.7",
            "source_type": "lock",
        }
    ]


def test_uv_environment_versions_and_root():
    content = b"""version = 1
[[package]]
name = "my-app"
version = "0.1.0"
source = { virtual = "." }
dependencies = [{name = "httpx"}]
[[package]]
name = "httpx"
version = "0.28.1"
source = { registry = "https://pypi.org/simple" }
dependencies = [{name = "colorama", marker = "sys_platform == 'win32'"}]
[[package]]
name = "colorama"
version = "0.4.6"
source = { registry = "https://pypi.org/simple" }
resolution-markers = ["sys_platform == 'win32'"]
"""
    result = parse("uv.lock", content, platform="linux")
    assert result.dependencies[0].direct is True
    assert result.dependencies[1].status == "excluded"
    assert result.edges == []


def test_machine_marker_is_uncertain_not_host_assumption():
    dep = parse(
        "requirements.txt", b"foo==1; platform_machine == 'arm64'"
    ).dependencies[0]
    assert dep.status == "uncertain"


def test_limits():
    with pytest.raises(InputError):
        parse("requirements.txt", b"x" * (1024 * 1024 + 1))
    with pytest.raises(InputError):
        parse(
            "requirements.txt", "\n".join(f"package{i}==1" for i in range(301)).encode()
        )
