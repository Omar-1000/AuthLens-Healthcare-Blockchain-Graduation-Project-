from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(r"C:\Users\abodk\Desktop\eheath-system")
OUT_DIR = ROOT / "poster"
OUT_PNG = OUT_DIR / "authlens-healthcare-blockchain-final.png"
OUT_PDF = OUT_DIR / "authlens-healthcare-blockchain-final.pdf"

LOGO_BLUE = Path(r"C:\Users\abodk\Desktop\images.png")
LOGO_AUTHLENS = Path(r"C:\Users\abodk\Desktop\ChatGPT_Image_May_20_2026_07_22_48_PM.png")
LOGO_UJ = Path(r"C:\Users\abodk\Desktop\University_of_Jordan_Logo.png")

W, H = 1600, 2400

NAVY = (2, 9, 54)
NAVY_2 = (6, 24, 92)
BLUE = (0, 93, 255)
CYAN = (25, 231, 255)
INK = (6, 19, 71)
MUTED = (48, 76, 140)
WHITE = (255, 255, 255)
PANEL = (248, 253, 255)

FONT_REG = r"C:\Windows\Fonts\segoeui.ttf"
FONT_SB = r"C:\Windows\Fonts\seguisb.ttf"
FONT_BOLD = r"C:\Windows\Fonts\seguibl.ttf"


def font(size, bold=False, semibold=False):
    path = FONT_BOLD if bold else FONT_SB if semibold else FONT_REG
    return ImageFont.truetype(path, size)


def blend(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_background():
    img = Image.new("RGB", (W, H), NAVY)
    px = img.load()
    for y in range(H):
        for x in range(W):
            t = (x + y * 0.45) / (W + H * 0.45)
            base = blend((1, 12, 62), (0, 101, 255), min(1, max(0, t)))
            cx, cy = W / 2, 290
            dist = ((x - cx) ** 2 / (900 ** 2) + (y - cy) ** 2 / (420 ** 2)) ** 0.5
            glow = max(0, 1 - dist)
            color = blend(base, (238, 253, 255), glow * 0.92)
            edge = min(x, W - x, y, H - y) / 180
            if edge < 1:
                color = blend((1, 8, 44), color, edge)
            px[x, y] = color
    return img.convert("RGBA")


def draw_circuit(draw):
    line = (25, 231, 255, 80)
    for step in range(0, W, 58):
        draw.line([(step, 0), (step, 500)], fill=line, width=1)
    for step in range(0, 560, 58):
        draw.line([(0, step), (W, step)], fill=(25, 231, 255, 55), width=1)
    for x, y, w, h in [
        (-40, 160, 260, 170),
        (1380, 260, 260, 180),
        (1280, 1980, 330, 220),
    ]:
        c = (25, 231, 255, 115)
        draw.line([(x, y), (x + w * 0.72, y), (x + w * 0.72, y + h * 0.42)], fill=c, width=3)
        draw.line([(x + w * 0.18, y + h * 0.72), (x + w, y + h * 0.72)], fill=c, width=3)
        draw.ellipse([x + w * 0.72 - 7, y + h * 0.42 - 7, x + w * 0.72 + 7, y + h * 0.42 + 7], fill=c)
        draw.ellipse([x + w * 0.18 - 7, y + h * 0.72 - 7, x + w * 0.18 + 7, y + h * 0.72 + 7], fill=c)


def rounded_gradient(base, box, radius, top, bottom, outline=None, width=2):
    x, y, w, h = box
    panel = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    ppx = panel.load()
    for yy in range(int(h)):
        t = yy / max(1, h - 1)
        color = blend(top, bottom, t)
        for xx in range(int(w)):
            ppx[xx, yy] = (*color, 255)
    mask = Image.new("L", (int(w), int(h)), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    base.paste(panel, (int(x), int(y)), mask)
    d = ImageDraw.Draw(base)
    if outline:
        d.rounded_rectangle([x, y, x + w, y + h], radius=radius, outline=outline, width=width)


def text_size(draw, text, fnt):
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def center_text(draw, xywh, text, fnt, fill, stroke_fill=None, stroke_width=0):
    x, y, w, h = xywh
    tw, th = text_size(draw, text, fnt)
    draw.text(
        (x + (w - tw) / 2, y + (h - th) / 2 - 2),
        text,
        font=fnt,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )


def wrap_text(draw, text, fnt, max_width):
    words = text.split()
    lines = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if text_size(draw, candidate, fnt)[0] <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def draw_wrapped(draw, text, x, y, max_width, fnt, fill, line_gap=8, align="left", stroke_width=0, stroke_fill=None):
    cur_y = y
    for line in wrap_text(draw, text, fnt, max_width):
        tw, th = text_size(draw, line, fnt)
        lx = x
        if align == "center":
            lx = x + (max_width - tw) / 2
        draw.text((lx, cur_y), line, font=fnt, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)
        cur_y += th + line_gap
    return cur_y


def ribbon(draw, x, y, w, h, title, number=None):
    cut = 48
    points = [
        (x + cut, y),
        (x + w - cut, y),
        (x + w, y + h / 2),
        (x + w - cut, y + h),
        (x + cut, y + h),
        (x, y + h / 2),
    ]
    draw.polygon(points, fill=(3, 20, 85), outline=CYAN)
    draw.line([(x + cut, y + 3), (x + w - cut, y + 3)], fill=(36, 191, 255), width=4)
    f = font(25, bold=True)
    label = title.upper()
    if number:
        badge = [x + 25, y + 8, x + 61, y + h - 8]
        draw.rounded_rectangle(badge, radius=8, fill=WHITE)
        center_text(draw, (badge[0], badge[1], badge[2] - badge[0], badge[3] - badge[1]), str(number), font(24, bold=True), (7, 34, 118))
        center_text(draw, (x + 70, y, w - 90, h), label, f, WHITE, stroke_fill=(0, 0, 0), stroke_width=1)
    else:
        center_text(draw, (x + 18, y, w - 36, h), label, f, WHITE, stroke_fill=(0, 0, 0), stroke_width=1)


def draw_person(draw, x, y, w, name, sid, show_right=True):
    draw.ellipse([x + 34, y + 17, x + 102, y + 85], fill=(7, 26, 95), outline=WHITE, width=3)
    draw.ellipse([x + 59, y + 30, x + 77, y + 48], fill=WHITE)
    draw.ellipse([x + 47, y + 54, x + 89, y + 84], fill=WHITE)
    draw.text((x + 124, y + 20), name, font=font(27, semibold=True), fill=WHITE, stroke_width=1, stroke_fill=(0, 0, 0))
    draw.text((x + 124, y + 56), sid, font=font(26, bold=True), fill=CYAN, stroke_width=1, stroke_fill=(0, 0, 0))
    if show_right:
        draw.line([(x + w, y + 20), (x + w, y + 82)], fill=CYAN, width=3)


def draw_logo(canvas, logo_path, card_box, fit_box):
    x, y, w, h = card_box
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=28, fill=(255, 255, 255, 194), outline=(25, 231, 255, 90), width=2)
    logo = Image.open(logo_path).convert("RGBA")
    fitted = ImageOps.contain(logo, fit_box, Image.Resampling.LANCZOS)
    px = int(x + (w - fitted.width) / 2)
    py = int(y + (h - fitted.height) / 2)
    canvas.alpha_composite(fitted, (px, py))
    draw.ellipse([x + 35, y + h - 42, x + w - 35, y + h + 20], outline=(25, 231, 255, 110), width=2)


def panel(draw, box, title, number=None, dark=False):
    x, y, w, h = box
    if dark:
        rounded_gradient(img, box, 22, (2, 11, 61), (5, 48, 137), outline=CYAN, width=2)
    else:
        rounded_gradient(img, box, 22, (251, 254, 255), (226, 246, 253), outline=BLUE, width=2)
    draw.rounded_rectangle([x + 5, y + 5, x + w - 5, y + h - 5], radius=18, outline=(255, 255, 255, 155), width=1)
    rw = min(w - 54, max(330, len(title) * 17 + 120))
    ribbon(draw, x + (w - rw) / 2, y - 20, rw, 52, title, number)


def bullet_list(draw, items, x, y, w, icon_labels, dark=False, size=24, gap=19):
    f = font(size, semibold=True)
    color = WHITE if dark else (7, 25, 109)
    icon_fill = WHITE if dark else None
    yy = y
    for idx, text in enumerate(items):
        icon = icon_labels[idx]
        if dark:
            draw.ellipse([x, yy + 3, x + 46, yy + 49], fill=icon_fill)
            center_text(draw, (x, yy + 4, 46, 44), icon, font(20, bold=True), (8, 32, 103))
            tx = x + 64
            max_w = w - 64
        else:
            draw.rounded_rectangle([x, yy, x + 58, yy + 58], radius=16, fill=(7, 29, 104), outline=CYAN, width=2)
            center_text(draw, (x, yy, 58, 58), icon, font(18, bold=True), WHITE)
            tx = x + 78
            max_w = w - 78
        next_y = draw_wrapped(draw, text, tx, yy + 1, max_w, f, color, line_gap=5)
        yy = max(yy + 64, next_y) + gap


def arrow(draw, start, end, fill=(5, 38, 126), width=5):
    draw.line([start, end], fill=fill, width=width)
    sx, sy = start
    ex, ey = end
    if ex >= sx:
        tri = [(ex, ey), (ex - 16, ey - 10), (ex - 16, ey + 10)]
    else:
        tri = [(ex, ey), (ex + 16, ey - 10), (ex + 16, ey + 10)]
    draw.polygon(tri, fill=fill)


def small_node(draw, box, text, fill=(255, 255, 255), text_fill=(7, 25, 109), size=18):
    x, y, w, h = box
    draw.rounded_rectangle([x, y, x + w, y + h], radius=15, fill=fill, outline=BLUE, width=2)
    draw_wrapped(draw, text, x + 8, y + 10, w - 16, font(size, bold=True), text_fill, line_gap=2, align="center")


def architecture(draw, box):
    x, y, w, h = box
    left_x = x + 18
    mid_x = x + 150
    right_x = x + 318
    top = y + 78
    for i, label in enumerate(["Patient", "Doctor", "Admin"]):
        small_node(draw, (left_x, top + i * 72, 94, 56), label, size=17)
    small_node(draw, (mid_x, top + 33, 132, 82), "Flask\nBackend", fill=(5, 42, 134), text_fill=WHITE, size=19)
    small_node(draw, (mid_x, top + 148, 132, 70), "Access\nControl", size=17)
    small_node(draw, (right_x, top, 126, 64), "MySQL\nDatabase", size=16)
    small_node(draw, (right_x, top + 82, 126, 64), "Blockchain\nLedger", size=16)
    small_node(draw, (right_x, top + 164, 126, 64), "Wallet +\nAI Modules", size=16)

    for yy in [top + 28, top + 100, top + 172]:
        arrow(draw, (left_x + 96, yy), (mid_x - 8, top + 74), width=4)
    arrow(draw, (mid_x + 132, top + 74), (right_x - 8, top + 32), width=4)
    arrow(draw, (mid_x + 132, top + 74), (right_x - 8, top + 114), width=4)
    arrow(draw, (mid_x + 132, top + 183), (right_x - 8, top + 196), width=4)
    note = "Data remains off-chain; hashes, versions, and identity proof are anchored on-chain."
    draw_wrapped(draw, note, x + 28, y + h - 82, w - 56, font(19, semibold=True), MUTED, line_gap=4, align="center")


def methodology(draw, box):
    x, y, w, h = box
    labels = [
        ("Analyze", "Roles, privacy risks, access flows, and trust gaps."),
        ("Design", "Patient consent, role access, encrypted storage, ledger proof."),
        ("Build", "Flask, MySQL, smart contract, MetaMask, OTP, CAPTCHA."),
        ("Verify", "Hash comparison, node votes, and tamper simulations."),
        ("Evaluate", "Privacy, usability, auditability, and access behavior."),
    ]
    step_w = (w - 96) / 5
    yy = y + 86
    for i, (title, body) in enumerate(labels):
        sx = x + 28 + i * (step_w + 10)
        draw.rounded_rectangle([sx, yy, sx + step_w, yy + 272], radius=20, fill=(255, 255, 255, 225), outline=BLUE, width=2)
        draw.rounded_rectangle([sx + step_w / 2 - 22, yy + 18, sx + step_w / 2 + 22, yy + 62], radius=12, fill=(6, 24, 92))
        center_text(draw, (sx + step_w / 2 - 22, yy + 18, 44, 44), str(i + 1), font(23, bold=True), WHITE)
        center_text(draw, (sx + 12, yy + 78, step_w - 24, 38), title.upper(), font(20, bold=True), (6, 24, 92))
        draw_wrapped(draw, body, sx + 16, yy + 130, step_w - 32, font(18, semibold=True), MUTED, line_gap=4, align="center")
        if i < 4:
            arrow(draw, (sx + step_w + 2, yy + 136), (sx + step_w + 24, yy + 136), width=4)


def feature_grid(draw, box):
    x, y, w, h = box
    features = [
        "Encrypted off-chain records",
        "Patient approval workflow",
        "Blockchain hash verification",
        "MetaMask wallet login",
        "OTP + CAPTCHA protection",
        "Role-based dashboards",
        "Record version history",
        "Audit logs and traceability",
        "Doctor account verification",
        "Prescription AI support",
    ]
    cell_w = (w - 88) / 2
    cell_h = 58
    row_gap = 9
    start_y = y + 72
    for i, feat in enumerate(features):
        col = i % 2
        row = i // 2
        cx = x + 28 + col * (cell_w + 20)
        cy = start_y + row * (cell_h + row_gap)
        draw.rounded_rectangle([cx, cy, cx + cell_w, cy + cell_h], radius=15, fill=(255, 255, 255, 236), outline=(0, 93, 255), width=2)
        draw_wrapped(draw, feat, cx + 12, cy + 8, cell_w - 24, font(16, bold=True), (7, 25, 109), line_gap=1, align="center")


def foundation_grid(draw, box):
    x, y, w, h = box
    techs = [
        "Flask\nBackend",
        "MySQL\nDatabase",
        "Solidity\nSmart Contract",
        "Web3 +\nGanache",
        "MetaMask\nWallet Auth",
        "OTP, CAPTCHA\nand Sessions",
    ]
    cell_w = (w - 86) / 2
    cell_h = 78
    for i, tech in enumerate(techs):
        col = i % 2
        row = i // 2
        cx = x + 28 + col * (cell_w + 18)
        cy = y + 78 + row * (cell_h + 15)
        draw.rounded_rectangle([cx, cy, cx + cell_w, cy + cell_h], radius=16, fill=(242, 253, 255), outline=CYAN, width=2)
        center_text(draw, (cx + 8, cy + 6, cell_w - 16, cell_h - 12), tech, font(21, bold=True), (7, 25, 109))


def workflow(draw, box):
    x, y, w, h = box
    panel(draw, box, "Secure Access Workflow", None)
    steps = [
        ("1", "DR", "Doctor\nrequests access"),
        ("2", "PT", "Patient\nreviews request"),
        ("3", "OK", "Patient\napproves or rejects"),
        ("4", "ID", "System verifies\nidentity + role"),
        ("5", "REC", "Encrypted record\naccess + hash proof"),
    ]
    gap = 36
    node_w = (w - 90 - gap * 4) / 5
    yy = y + 84
    for i, (num, code, text) in enumerate(steps):
        nx = x + 45 + i * (node_w + gap)
        draw.ellipse([nx + node_w / 2 - 44, yy, nx + node_w / 2 + 44, yy + 88], fill=(238, 253, 255), outline=BLUE, width=3)
        center_text(draw, (nx + node_w / 2 - 44, yy, 88, 88), code, font(24, bold=True), (7, 25, 109))
        draw.ellipse([nx + node_w / 2 - 58, yy - 14, nx + node_w / 2 - 14, yy + 30], fill=(6, 24, 92), outline=CYAN, width=2)
        center_text(draw, (nx + node_w / 2 - 58, yy - 14, 44, 44), num, font(22, bold=True), WHITE)
        draw_wrapped(draw, text.replace("\n", " "), nx, yy + 108, node_w, font(22, bold=True), (7, 25, 109), line_gap=2, align="center")
        if i < 4:
            arrow(draw, (nx + node_w + 8, yy + 44), (nx + node_w + gap - 6, yy + 44), width=6)


img = make_background()
draw = ImageDraw.Draw(img)
draw_circuit(draw)

draw.rounded_rectangle([55, 30, 1545, 132], radius=22, fill=(3, 17, 70), outline=(168, 245, 255), width=2)
draw_person(draw, 70, 30, 488, "Omar Ayesh", "0226526")
draw_person(draw, 570, 30, 488, "Abdalrahman Khalil", "0227165")
draw_person(draw, 1070, 30, 455, "Abdalrahman Abujeep", "0227653", show_right=False)

super_poly = [(390, 128), (1210, 128), (1138, 194), (462, 194)]
draw.polygon(super_poly, fill=(3, 17, 70), outline=(25, 231, 255))
center_text(draw, (390, 126, 820, 66), "Supervisor: Dr. Oraib Abualghanam", font(34, bold=True), WHITE, stroke_fill=(0, 0, 0), stroke_width=1)

draw_logo(img, LOGO_BLUE, (76, 224, 300, 258), (212, 212))
draw_logo(img, LOGO_AUTHLENS, (633, 202, 334, 282), (258, 258))
draw_logo(img, LOGO_UJ, (1224, 224, 300, 258), (206, 256))

title = "AuthLens Healthcare Blockchain"
center_text(draw, (80, 508, 1440, 90), title, font(77, bold=True), (5, 17, 65), stroke_fill=WHITE, stroke_width=3)
ribbon(draw, 226, 608, 1148, 58, "Protecting Sensitive Healthcare Data from Cyber Attacks")
draw.rounded_rectangle([176, 668, 1424, 780], radius=20, fill=(255, 255, 255, 222), outline=(25, 231, 255), width=2)
center_text(
    draw,
    (210, 690, 1180, 36),
    "AuthLens gives patients control over access to sensitive healthcare data.",
    font(27, semibold=True),
    (9, 31, 111),
)
center_text(
    draw,
    (210, 728, 1180, 36),
    "It uses encrypted off-chain storage, blockchain integrity proof, and identity-aware approvals.",
    font(27, semibold=True),
    (9, 31, 111),
)

row1_y = 790
box_w = 496
gap = 22
problem_box = (34, row1_y, box_w, 430)
solution_box = (34 + box_w + gap, row1_y, box_w, 430)
arch_box = (34 + (box_w + gap) * 2, row1_y, box_w, 430)

panel(draw, problem_box, "Problem", "1")
bullet_list(
    draw,
    [
        "Unauthorized access to sensitive patient records.",
        "Weak identity verification in digital healthcare systems.",
        "Medical data can be modified without clear tamper proof.",
        "Patients have limited visibility over who views their data.",
    ],
    problem_box[0] + 36,
    problem_box[1] + 80,
    problem_box[2] - 72,
    ["!", "ID", "H", "V"],
)

panel(draw, solution_box, "Solution", "2")
bullet_list(
    draw,
    [
        "Patient-approved access before a doctor can view records.",
        "Blockchain hashes anchor record integrity and approvals.",
        "Encrypted medical records remain off-chain for privacy.",
        "Wallet authentication and audit logs improve accountability.",
    ],
    solution_box[0] + 36,
    solution_box[1] + 80,
    solution_box[2] - 72,
    ["OK", "BC", "L", "W"],
)

panel(draw, arch_box, "System Architecture", "3")
architecture(draw, arch_box)

method_box = (34, 1246, 1004, 430)
features_box = (1060, 1246, 506, 430)
panel(draw, method_box, "Methodology", "4")
methodology(draw, method_box)
panel(draw, features_box, "Features", "5")
feature_grid(draw, features_box)

conclusion_box = (34, 1702, 800, 340)
foundation_box = (858, 1702, 708, 340)
panel(draw, conclusion_box, "Conclusion", "6", dark=True)
bullet_list(
    draw,
    [
        "Enhances patient privacy and control over medical data.",
        "Strengthens trust by making record changes tamper-evident.",
        "Supports secure digital healthcare with clear audit trails.",
    ],
    conclusion_box[0] + 40,
    conclusion_box[1] + 82,
    conclusion_box[2] - 80,
    ["OK", "OK", "OK"],
    dark=True,
    size=25,
    gap=17,
)

panel(draw, foundation_box, "Technology Foundation")
foundation_grid(draw, foundation_box)

workflow_box = (34, 2068, 1532, 244)
workflow(draw, workflow_box)

draw.rectangle([34, 2330, 1566, 2374], fill=(2, 9, 54, 205))
center_text(
    draw,
    (34, 2330, 1532, 44),
    "AuthLens Healthcare Blockchain | Secure Access, Patient Control, Blockchain Integrity",
    font(19, bold=True),
    WHITE,
)

draw.rounded_rectangle([4, 4, W - 5, H - 5], radius=0, outline=(159, 244, 255), width=4)

OUT_DIR.mkdir(parents=True, exist_ok=True)
rgb = Image.new("RGB", img.size, WHITE)
rgb.paste(img, mask=img.getchannel("A"))
rgb.save(OUT_PNG, quality=96)
rgb.save(OUT_PDF, "PDF", resolution=150.0)
print(f"Wrote {OUT_PNG}")
print(f"Wrote {OUT_PDF}")
