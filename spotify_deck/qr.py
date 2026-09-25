# -*- coding: utf-8 -*-
"""
Generatore di QR code minimale, puro Python (nessuna dipendenza esterna).

Supporta la modalita' "byte" (qualunque testo/URL in UTF-8) e le versioni
QR 1-6 a livello di correzione errori M (medio, ~15% di ridondanza) --
capacita' fino a 108 byte, ampiamente sufficiente per un URL o un tag.
Non implementa il blocco "informazioni di versione" (necessario solo dalla
versione 7 in su), quindi resta volutamente entro la versione 6.

generate(text) -> matrice di bool (True = modulo scuro), col quiet zone
di 4 moduli gia' inclusa su tutti i lati.
"""

# ---------------------------------------------------------------- GF(256)
_EXP = [0] * 512
_LOG = [0] * 256


def _init_gf():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_gf()


def _gmul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(ec_count):
    poly = [1]
    for i in range(ec_count):
        new = [0] * (len(poly) + 1)
        for j, c in enumerate(poly):
            new[j] ^= _gmul(c, 1)
            new[j + 1] ^= _gmul(c, _EXP[i])
        poly = new
    return poly


def _rs_encode(data, ec_count):
    gen = _rs_generator(ec_count)
    res = list(data) + [0] * ec_count
    for i in range(len(data)):
        coef = res[i]
        if coef:
            for j, g in enumerate(gen):
                res[i + j] ^= _gmul(g, coef)
    return res[len(data):]


# ---------------------------------------------------------------- tabelle versione (livello M)
# (capacita' dati in codeword, ec per blocco, blocchi gruppo1, dc gruppo1, blocchi gruppo2, dc gruppo2)
_VTABLE = {
    1: (16, 10, 1, 16, 0, 0),
    2: (28, 16, 1, 28, 0, 0),
    3: (44, 26, 1, 44, 0, 0),
    4: (64, 18, 2, 32, 0, 0),
    5: (86, 24, 2, 43, 0, 0),
    6: (108, 16, 4, 27, 0, 0),
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}
_REMAINDER = {1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7}
_FMT_GEN = 0x537
_FMT_MASK = 0x5412


def _bch_format(data5):
    rem = data5 << 10
    for i in range(4, -1, -1):
        if rem & (1 << (i + 10)):
            rem ^= _FMT_GEN << i
    return ((data5 << 10) | rem) ^ _FMT_MASK


def _pick_version(nbytes):
    for v in range(1, 7):
        dc = _VTABLE[v][0]
        header_bits = 4 + 8               # modo byte + contatore (<=9: 8 bit)
        if header_bits + 8 * nbytes <= dc * 8:
            return v
    raise ValueError("testo troppo lungo per una QR versione 1-6 (max ~101 byte)")


def _data_bits(text, version):
    data = text.encode("utf-8")
    bits = "0100" + format(len(data), "08b")
    for b in data:
        bits += format(b, "08b")
    cap_bits = _VTABLE[version][0] * 8
    bits += "0" * min(4, cap_bits - len(bits))
    bits += "0" * ((8 - len(bits) % 8) % 8)
    pad = ["11101100", "00010001"]
    i = 0
    while len(bits) < cap_bits:
        bits += pad[i % 2]
        i += 1
    return bits


def _codewords(bits):
    return [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]


def _interleave(data_cw, version):
    _, ec_per_block, g1n, g1dc, g2n, g2dc = _VTABLE[version]
    blocks = []
    off = 0
    for _ in range(g1n):
        blocks.append(data_cw[off:off + g1dc])
        off += g1dc
    for _ in range(g2n):
        blocks.append(data_cw[off:off + g2dc])
        off += g2dc
    ec_blocks = [_rs_encode(b, ec_per_block) for b in blocks]
    out = []
    maxdc = max(len(b) for b in blocks)
    for i in range(maxdc):
        for b in blocks:
            if i < len(b):
                out.append(b[i])
    for i in range(ec_per_block):
        for eb in ec_blocks:
            out.append(eb[i])
    return out


# ---------------------------------------------------------------- matrice
_DARK, _LIGHT, _RESV = 1, 0, -1


def _new_matrix(size):
    return [[_RESV for _ in range(size)] for _ in range(size)]


def _set_square(m, r, c, size, val):
    for i in range(size):
        for j in range(size):
            m[r + i][c + j] = val


def _place_finder(m, r, c):
    n = len(m)
    for i in range(-1, 8):
        for j in range(-1, 8):
            rr, cc = r + i, c + j
            if not (0 <= rr < n and 0 <= cc < n):
                continue
            if 0 <= i <= 6 and 0 <= j <= 6 and (i in (0, 6) or j in (0, 6)):
                m[rr][cc] = _DARK
            elif 2 <= i <= 4 and 2 <= j <= 4:
                m[rr][cc] = _DARK
            else:
                m[rr][cc] = _LIGHT


def _place_alignment(m, r, c):
    for i in range(-2, 3):
        for j in range(-2, 3):
            if max(abs(i), abs(j)) == 1:
                m[r + i][c + j] = _LIGHT
            else:
                m[r + i][c + j] = _DARK


def _build_skeleton(version):
    size = 21 + 4 * (version - 1)
    m = _new_matrix(size)
    _place_finder(m, 0, 0)
    _place_finder(m, 0, size - 7)
    _place_finder(m, size - 7, 0)
    for i in range(8):                              # separatori (gia' LIGHT di default fuori raggio finder)
        for (r, c) in ((7, i), (i, 7), (7, size - 1 - i), (i, size - 8),
                       (size - 1 - i, 7), (size - 8, i)):
            if 0 <= r < size and 0 <= c < size:
                m[r][c] = _LIGHT
    coords = _ALIGN[version]
    for r in coords:
        for c in coords:
            if (r <= 8 and c <= 8) or (r <= 8 and c >= size - 9) or (r >= size - 9 and c <= 8):
                continue
            _place_alignment(m, r, c)
    for i in range(8, size - 8):                     # timing pattern
        v = _DARK if i % 2 == 0 else _LIGHT
        m[6][i] = v
        m[i][6] = v
    m[size - 8][8] = _DARK                            # modulo scuro fisso
    for i in range(9):                                # aree riservate per format info
        if m[8][i] == _RESV:
            m[8][i] = _LIGHT
        if m[i][8] == _RESV:
            m[i][8] = _LIGHT
    for i in range(8):
        if m[8][size - 1 - i] == _RESV:
            m[8][size - 1 - i] = _LIGHT
        if m[size - 1 - i][8] == _RESV:
            m[size - 1 - i][8] = _LIGHT
    return m


def _place_data(m, bits):
    size = len(m)
    it = iter(bits)
    col = size - 1
    going_up = True
    while col > 0:
        if col == 6:                                  # salta la colonna del timing pattern
            col -= 1
            continue
        rows = range(size - 1, -1, -1) if going_up else range(size)
        for r in rows:
            for c in (col, col - 1):
                if m[r][c] == _RESV:
                    try:
                        bit = next(it)
                    except StopIteration:
                        bit = "0"
                    m[r][c] = _DARK if bit == "1" else _LIGHT
        going_up = not going_up
        col -= 2


def _mask_fn(i):
    return [
        lambda r, c: (r + c) % 2 == 0,
        lambda r, c: r % 2 == 0,
        lambda r, c: c % 3 == 0,
        lambda r, c: (r + c) % 3 == 0,
        lambda r, c: (r // 2 + c // 3) % 2 == 0,
        lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
        lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
        lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
    ][i]


def _apply_mask(skel, data_m, mask_i):
    size = len(skel)
    f = _mask_fn(mask_i)
    out = [row[:] for row in data_m]
    for r in range(size):
        for c in range(size):
            if skel[r][c] == _RESV and f(r, c):
                out[r][c] = _DARK if out[r][c] == _LIGHT else _LIGHT
    return out


def _penalty(m):
    size = len(m)
    p = 0
    for r in range(size):
        run, cur = 1, m[r][0]
        for c in range(1, size):
            if m[r][c] == cur:
                run += 1
            else:
                if run >= 5:
                    p += run - 2
                run, cur = 1, m[r][c]
        if run >= 5:
            p += run - 2
    for c in range(size):
        run, cur = 1, m[0][c]
        for r in range(1, size):
            if m[r][c] == cur:
                run += 1
            else:
                if run >= 5:
                    p += run - 2
                run, cur = 1, m[r][c]
        if run >= 5:
            p += run - 2
    for r in range(size - 1):
        for c in range(size - 1):
            v = m[r][c]
            if v == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                p += 3
    patt = [_DARK, _LIGHT, _DARK, _DARK, _DARK, _LIGHT, _DARK]
    for r in range(size):
        for c in range(size - 6):
            if [m[r][c + k] for k in range(7)] == patt:
                p += 40
    for c in range(size):
        for r in range(size - 6):
            if [m[r + k][c] for k in range(7)] == patt:
                p += 40
    dark = sum(row.count(_DARK) for row in m)
    pct = 100 * dark / (size * size)
    p += int(abs(pct - 50) // 5) * 10
    return p


def generate(text):
    """Ritorna una matrice di bool (True = modulo scuro) con quiet zone inclusa."""
    version = _pick_version(len(text.encode("utf-8")))
    bits = _data_bits(text, version)
    cw = _interleave(_codewords(bits), version)
    bitstream = "".join(format(b, "08b") for b in cw) + "0" * _REMAINDER[version]
    skel = _build_skeleton(version)
    data_m = [row[:] for row in skel]
    _place_data(data_m, bitstream)
    best, best_p, best_i = None, None, 0
    for i in range(8):
        cand = _apply_mask(skel, data_m, i)
        p = _penalty(cand)
        if best_p is None or p < best_p:
            best, best_p, best_i = cand, p, i
    fmt = _bch_format((0b00 << 3) | best_i)            # livello M = 00
    size = len(best)
    for k in range(6):
        best[k][8] = _DARK if (fmt >> k) & 1 else _LIGHT
    best[7][8] = _DARK if (fmt >> 6) & 1 else _LIGHT
    best[8][8] = _DARK if (fmt >> 7) & 1 else _LIGHT
    best[8][7] = _DARK if (fmt >> 8) & 1 else _LIGHT
    for k in range(9, 15):
        best[8][14 - k] = _DARK if (fmt >> k) & 1 else _LIGHT
    for k in range(8):
        best[8][size - 1 - k] = _DARK if (fmt >> k) & 1 else _LIGHT
    for k in range(7):
        best[size - 1 - k][8] = _DARK if (fmt >> (14 - k)) & 1 else _LIGHT
    quiet = 4
    out = [[False] * (size + 2 * quiet) for _ in range(size + 2 * quiet)]
    for r in range(size):
        for c in range(size):
            out[r + quiet][c + quiet] = (best[r][c] == _DARK)
    return out
