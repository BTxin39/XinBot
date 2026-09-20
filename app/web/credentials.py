import hashlib
import os
from pathlib import Path
import re

from dotenv import set_key, unset_key


def credential_name(provider: str) -> str:
    digest = hashlib.sha256(provider.encode("utf-8")).hexdigest()[:24].upper()
    return f"XINBOT_PROVIDER_{digest}_API_KEY"


def validate_secret(secret: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._~+/=:-]{1,4096}", secret):
        raise ValueError("密钥包含不支持的字符，不能包含空白、引号、变量表达式或控制字符")
    return secret


def write_secret(root: Path, name: str, secret: str | None):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,180}_API_KEY", name, re.IGNORECASE):
        raise ValueError("此环境变量不允许由网页修改")
    path = root / ".env"
    if path.is_symlink():
        raise ValueError("密钥文件不能是符号链接")
    if secret is not None:
        validate_secret(secret)
        if not path.exists():
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        set_key(str(path), name, secret, quote_mode="always")
        os.environ[name] = secret
    else:
        if path.exists():
            unset_key(str(path), name)
        os.environ.pop(name, None)
    if os.name != "nt" and path.exists():
        path.chmod(0o600)
