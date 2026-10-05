"""Envelope used by JLCPCB colour files (port of TransJLC colorful/encrypt.rs).

    file = RSA-OAEP-SHA256(aes_key) || RSA-OAEP-SHA256(aes_iv) || AES-128-GCM(svg) || tag

AES-GCM uses a 16-byte nonce (WebCrypto behaviour), so J0 is derived with GHASH.
KiCad's bundled Python has no `cryptography`, hence a pure-Python fallback.
Backends, fastest first: `cryptography`, OpenSSL libcrypto via ctypes, pure Python.
"""
import base64
import hashlib
import os

from .errors import ColorSilkError

JLC_RSA_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAzPtuUqJecaR/wWtctGT8
QuVslmDH3Ut3s8c1Ls4A+M9rwpeLjgDUqfcrSrTHBrl5k/dOeJEWMeNF7STWS5jo
WZE0H60cvf2bhormC9S6CRwq4Lw0ua0YQMo66R/qCtLVa5w6WkaPCz4b0xaHWtej
JH49C0T67rU2DkepXuMPpwNCflMU+WgEQioZEldUTD6gYpu2U5GrW4AE0AQiIo+j
e7tgN8PlBMbMaEfu0LokZyth1ugfuLAgyogWnedAegQmPZzAUe36Sni94AsDlhxm
mjFl+WQZzD3MclbEY6KQB5XL8zCR/J6pCUUwfHantLxY/gQi0XJG5hWWtDyH/fR2
lwIDAQAB
-----END PUBLIC KEY-----"""


# --------------------------------------------------------------------------- DER / PEM

def _pem_der(pem):
    lines = [l.strip() for l in pem.strip().splitlines() if l.strip() and not l.startswith("-----")]
    return base64.b64decode("".join(lines))


def _der_read(data, pos):
    tag = data[pos]
    length = data[pos + 1]
    pos += 2
    if length & 0x80:
        n = length & 0x7F
        length = int.from_bytes(data[pos:pos + n], "big")
        pos += n
    return tag, data[pos:pos + length], pos + length


def _der_ints(seq):
    out, pos = [], 0
    while pos < len(seq):
        tag, value, pos = _der_read(seq, pos)
        if tag == 0x02:
            out.append(int.from_bytes(value, "big"))
    return out


def load_public_key(pem):
    """SubjectPublicKeyInfo PEM -> (n, e)."""
    _, spki, _ = _der_read(_pem_der(pem), 0)
    _, _, pos = _der_read(spki, 0)                 # AlgorithmIdentifier
    tag, bitstring, _ = _der_read(spki, pos)       # BIT STRING
    if tag != 0x03:
        raise ValueError("SPKI sans BIT STRING")
    _, rsa_seq, _ = _der_read(bitstring[1:], 0)
    n, e = _der_ints(rsa_seq)[:2]
    return n, e


def load_private_key(pem):
    """PKCS#1 or PKCS#8 RSA private key PEM -> (n, e, d). Test use only."""
    _, seq, _ = _der_read(_pem_der(pem), 0)
    ints = _der_ints(seq)
    if len(ints) < 3:  # PKCS#8: version, AlgorithmIdentifier, OCTET STRING(PKCS#1)
        pos = 0
        _, _, pos = _der_read(seq, pos)
        _, _, pos = _der_read(seq, pos)
        _, octets, _ = _der_read(seq, pos)
        _, seq, _ = _der_read(octets, 0)
        ints = _der_ints(seq)
    return ints[1], ints[2], ints[3]


# --------------------------------------------------------------------------- RSA-OAEP (SHA-256)

def _mgf1(seed, length):
    out = b""
    counter = 0
    while len(out) < length:
        out += hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return out[:length]


def _xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def rsa_oaep_encrypt(n, e, message, rand=os.urandom):
    k = (n.bit_length() + 7) // 8
    h_len = 32
    if len(message) > k - 2 * h_len - 2:
        raise ValueError("message trop long pour RSA-OAEP")
    l_hash = hashlib.sha256(b"").digest()
    db = l_hash + b"\x00" * (k - len(message) - 2 * h_len - 2) + b"\x01" + message
    seed = rand(h_len)
    masked_db = _xor(db, _mgf1(seed, k - h_len - 1))
    masked_seed = _xor(seed, _mgf1(masked_db, h_len))
    em = b"\x00" + masked_seed + masked_db
    return pow(int.from_bytes(em, "big"), e, n).to_bytes(k, "big")


def rsa_oaep_decrypt(n, d, ciphertext):
    k = (n.bit_length() + 7) // 8
    h_len = 32
    em = pow(int.from_bytes(ciphertext, "big"), d, n).to_bytes(k, "big")
    masked_seed, masked_db = em[1:1 + h_len], em[1 + h_len:]
    seed = _xor(masked_seed, _mgf1(masked_db, h_len))
    db = _xor(masked_db, _mgf1(seed, k - h_len - 1))
    if em[0] != 0 or db[:h_len] != hashlib.sha256(b"").digest():
        raise ValueError("déchiffrement OAEP invalide")
    return db[db.index(b"\x01", h_len) + 1:]


# --------------------------------------------------------------------------- AES-128 (pure Python)

def _build_tables():
    sbox = [0] * 256
    p = q = 1
    while True:
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1 | q >> 7) & 0xFF) ^ ((q << 2 | q >> 6) & 0xFF) ^ ((q << 3 | q >> 5) & 0xFF) \
            ^ ((q << 4 | q >> 4) & 0xFF)
        sbox[p] = x ^ 0x63
        if p == 1:
            break
    sbox[0] = 0x63

    def xt(a):
        return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1

    t0 = []
    for s in sbox:
        s2 = xt(s)
        t0.append((s2 << 24) | (s << 16) | (s << 8) | (s2 ^ s))
    t1 = [((v >> 8) | (v << 24)) & 0xFFFFFFFF for v in t0]
    t2 = [((v >> 16) | (v << 16)) & 0xFFFFFFFF for v in t0]
    t3 = [((v >> 24) | (v << 8)) & 0xFFFFFFFF for v in t0]
    return sbox, t0, t1, t2, t3


_SBOX, _T0, _T1, _T2, _T3 = _build_tables()


class _AES128:
    def __init__(self, key):
        w = [int.from_bytes(key[i:i + 4], "big") for i in range(0, 16, 4)]
        rcon = 1
        for i in range(4, 44):
            t = w[i - 1]
            if i % 4 == 0:
                t = ((t << 8) | (t >> 24)) & 0xFFFFFFFF
                t = (_SBOX[t >> 24] << 24) | (_SBOX[(t >> 16) & 255] << 16) | (_SBOX[(t >> 8) & 255] << 8) | _SBOX[t & 255]
                t ^= rcon << 24
                rcon = ((rcon << 1) ^ 0x1B) & 0xFF if rcon & 0x80 else rcon << 1
            w.append(w[i - 4] ^ t)
        self.rk = w

    def encrypt_block(self, block_int):
        rk, T0, T1, T2, T3, S = self.rk, _T0, _T1, _T2, _T3, _SBOX
        s0 = (block_int >> 96) ^ rk[0]
        s1 = ((block_int >> 64) & 0xFFFFFFFF) ^ rk[1]
        s2 = ((block_int >> 32) & 0xFFFFFFFF) ^ rk[2]
        s3 = (block_int & 0xFFFFFFFF) ^ rk[3]
        for r in range(1, 10):
            k = 4 * r
            t0 = T0[s0 >> 24] ^ T1[(s1 >> 16) & 255] ^ T2[(s2 >> 8) & 255] ^ T3[s3 & 255] ^ rk[k]
            t1 = T0[s1 >> 24] ^ T1[(s2 >> 16) & 255] ^ T2[(s3 >> 8) & 255] ^ T3[s0 & 255] ^ rk[k + 1]
            t2 = T0[s2 >> 24] ^ T1[(s3 >> 16) & 255] ^ T2[(s0 >> 8) & 255] ^ T3[s1 & 255] ^ rk[k + 2]
            t3 = T0[s3 >> 24] ^ T1[(s0 >> 16) & 255] ^ T2[(s1 >> 8) & 255] ^ T3[s2 & 255] ^ rk[k + 3]
            s0, s1, s2, s3 = t0, t1, t2, t3
        o0 = ((S[s0 >> 24] << 24) | (S[(s1 >> 16) & 255] << 16) | (S[(s2 >> 8) & 255] << 8) | S[s3 & 255]) ^ rk[40]
        o1 = ((S[s1 >> 24] << 24) | (S[(s2 >> 16) & 255] << 16) | (S[(s3 >> 8) & 255] << 8) | S[s0 & 255]) ^ rk[41]
        o2 = ((S[s2 >> 24] << 24) | (S[(s3 >> 16) & 255] << 16) | (S[(s0 >> 8) & 255] << 8) | S[s1 & 255]) ^ rk[42]
        o3 = ((S[s3 >> 24] << 24) | (S[(s0 >> 16) & 255] << 16) | (S[(s1 >> 8) & 255] << 8) | S[s2 & 255]) ^ rk[43]
        return (o0 << 96) | (o1 << 64) | (o2 << 32) | o3


class _GHash:
    """GHASH with 16 x 256 precomputed tables (Shoup-style, byte at a time)."""
    R = 0xE1 << 120

    def __init__(self, h):
        v = h
        singles = []
        for _ in range(128):
            singles.append(v)
            v = (v >> 1) ^ (self.R if v & 1 else 0)
        self.tables = []
        for k in range(16):
            table = [0] * 256
            for b in range(256):
                acc = 0
                for j in range(8):
                    if b & (0x80 >> j):
                        acc ^= singles[8 * k + j]
                table[b] = acc
            self.tables.append(table)

    def mul(self, x):
        t = self.tables
        z = 0
        for k in range(16):
            z ^= t[k][(x >> (120 - 8 * k)) & 0xFF]
        return z

    def digest(self, data_blocks_int, y=0):
        for blk in data_blocks_int:
            y = self.mul(y ^ blk)
        return y


def _blocks(data):
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        yield int.from_bytes(chunk + b"\x00" * (16 - len(chunk)), "big")


def _gcm_python(key, iv, data, decrypt=False, tag=None):
    aes = _AES128(key)
    gh = _GHash(aes.encrypt_block(0))
    if len(iv) == 12:
        j0 = int.from_bytes(iv + b"\x00\x00\x00\x01", "big")
    else:
        j0 = gh.digest(list(_blocks(iv)) + [len(iv) * 8])
    ctr_hi = j0 & ~0xFFFFFFFF
    ctr_lo = j0 & 0xFFFFFFFF
    out = bytearray(len(data))
    enc = aes.encrypt_block
    for n, i in enumerate(range(0, len(data), 16)):
        ks = enc(ctr_hi | ((ctr_lo + 1 + n) & 0xFFFFFFFF)).to_bytes(16, "big")
        chunk = data[i:i + 16]
        out[i:i + len(chunk)] = (int.from_bytes(chunk, "big") ^ int.from_bytes(ks[:len(chunk)], "big")).to_bytes(len(chunk), "big")
    ciphertext = data if decrypt else bytes(out)
    s = gh.digest(_blocks(ciphertext))
    s = gh.mul(s ^ (len(ciphertext) * 8))  # len(A)=0 in the high 64 bits
    full_tag = (s ^ enc(j0)).to_bytes(16, "big")
    if decrypt:
        if full_tag != tag:
            raise ValueError("tag GCM invalide")
        return bytes(out)
    return bytes(out) + full_tag


# --------------------------------------------------------------------------- OpenSSL via ctypes

def _gcm_openssl(key, iv, data):
    import ctypes
    import ctypes.util
    import ssl  # noqa: F401  (loads the libcrypto bundled with this Python)

    lib = None
    candidates = ["libcrypto-3-x64", "libcrypto-3", "libcrypto-1_1-x64", "libcrypto-1_1",
                  ctypes.util.find_library("crypto"), "libcrypto.so.3", "libcrypto.3.dylib"]
    for name in [c for c in candidates if c]:
        try:
            lib = ctypes.CDLL(name)
            break
        except OSError:
            continue
    if lib is None:
        raise OSError("libcrypto introuvable")
    vp = ctypes.c_void_p
    lib.EVP_CIPHER_CTX_new.restype = vp
    lib.EVP_aes_128_gcm.restype = vp
    lib.EVP_EncryptInit_ex.argtypes = [vp, vp, vp, ctypes.c_char_p, ctypes.c_char_p]
    lib.EVP_CIPHER_CTX_ctrl.argtypes = [vp, ctypes.c_int, ctypes.c_int, vp]
    lib.EVP_EncryptUpdate.argtypes = [vp, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int), ctypes.c_char_p, ctypes.c_int]
    lib.EVP_EncryptFinal_ex.argtypes = [vp, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    lib.EVP_CIPHER_CTX_free.argtypes = [vp]
    EVP_CTRL_GCM_SET_IVLEN, EVP_CTRL_GCM_GET_TAG = 0x9, 0x10

    ctx = lib.EVP_CIPHER_CTX_new()
    try:
        ok = lib.EVP_EncryptInit_ex(ctx, lib.EVP_aes_128_gcm(), None, None, None)
        ok &= lib.EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, len(iv), None)
        ok &= lib.EVP_EncryptInit_ex(ctx, None, None, key, iv)
        out = ctypes.create_string_buffer(len(data) + 16)
        n = ctypes.c_int(0)
        ok &= lib.EVP_EncryptUpdate(ctx, out, ctypes.byref(n), data, len(data))
        m = ctypes.c_int(0)
        ok &= lib.EVP_EncryptFinal_ex(ctx, ctypes.cast(ctypes.addressof(out) + n.value, ctypes.c_char_p), ctypes.byref(m))
        tag = ctypes.create_string_buffer(16)
        ok &= lib.EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, 16, ctypes.cast(tag, vp))
        if ok != 1:
            raise OSError("échec EVP AES-GCM")
        return out.raw[:n.value + m.value] + tag.raw
    finally:
        lib.EVP_CIPHER_CTX_free(ctx)


def _gcm_cryptography(key, iv, data):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).encrypt(iv, data, None)


_GCM_BACKENDS = [("cryptography", _gcm_cryptography), ("openssl", _gcm_openssl), ("python", _gcm_python)]
_selected = None


def aes_gcm_encrypt(key, iv, data, backend=None):
    """Return ciphertext || 16-byte tag. Picks (and caches) the first working backend."""
    global _selected
    if backend:
        return dict(_GCM_BACKENDS)[backend](key, iv, data)
    if _selected:
        return _selected[1](key, iv, data)
    expected = _gcm_python(bytes(16), bytes(16), b"probe")
    errors = []
    for name, fn in _GCM_BACKENDS:
        try:
            if fn(bytes(16), bytes(16), b"probe") == expected:
                _selected = (name, fn)
                return fn(key, iv, data)
            errors.append(name + ": résultat incorrect")
        except Exception as e:
            errors.append("{}: {}".format(name, e))
    raise ColorSilkError("E_CRYPTO_BACKEND", "Aucun moteur AES-GCM : " + "; ".join(errors))


def selected_backend():
    return _selected[0] if _selected else None


def aes_gcm_decrypt(key, iv, data_with_tag):
    return _gcm_python(key, iv, data_with_tag[:-16], decrypt=True, tag=data_with_tag[-16:])


# --------------------------------------------------------------------------- envelope

class KeyMaterial:
    """One AES key/IV pair per export, like TransJLC (shared by all files)."""

    def __init__(self, public_key_pem=JLC_RSA_PUBLIC_KEY_PEM, aes_key=None, aes_iv=None, rand=os.urandom):
        try:
            n, e = load_public_key(public_key_pem)
        except Exception as ex:
            raise ColorSilkError("E_CRYPTO_BACKEND", "Clé publique RSA invalide : {}".format(ex))
        self.aes_key = aes_key or rand(16)
        self.aes_iv = aes_iv or rand(16)
        self.enc_key = rsa_oaep_encrypt(n, e, self.aes_key, rand)
        self.enc_iv = rsa_oaep_encrypt(n, e, self.aes_iv, rand)
        self.rsa_bytes = (n.bit_length() + 7) // 8


def encrypt_svg(svg_text, key_material):
    data = svg_text.encode("utf-8") if isinstance(svg_text, str) else svg_text
    return key_material.enc_key + key_material.enc_iv + aes_gcm_encrypt(key_material.aes_key, key_material.aes_iv, data)


def decrypt_file(blob, private_key_pem):
    """Inverse of encrypt_svg, for tests with a locally generated key pair."""
    n, _, d = load_private_key(private_key_pem)
    k = (n.bit_length() + 7) // 8
    key = rsa_oaep_decrypt(n, d, blob[:k])
    iv = rsa_oaep_decrypt(n, d, blob[k:2 * k])
    return aes_gcm_decrypt(key, iv, blob[2 * k:])
