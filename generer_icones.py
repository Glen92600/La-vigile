#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Icônes thèmes de veille — version premium (supersampling + relief)."""
from PIL import Image, ImageDraw, ImageFilter
import math, os

OUT = "/Users/gouerdane/Downloads/Veille médias/site/images"
N   = 256          # taille finale
SS  = 4            # facteur de supersampling
T   = N * SS       # taille de travail

WHITE = (255, 255, 255)

# ── Utils couleur ──────────────────────────────────────────────────────────────
def lighten(c, f):
    return tuple(min(255, int(v + (255 - v) * f)) for v in c)
def darken(c, f):
    return tuple(max(0, int(v * (1 - f))) for v in c)

# ── Fond : tuile dégradée + relief ─────────────────────────────────────────────
def make_tile(base):
    top    = lighten(base, 0.22)
    bottom = darken(base, 0.16)
    tile = Image.new("RGB", (T, T), base)
    px = tile.load()
    for y in range(T):
        t = y / (T - 1)
        # easing doux
        t = t * t * (3 - 2 * t)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(T):
            px[x, y] = (r, g, b)

    # Halo lumineux en haut à gauche (radial doux)
    halo = Image.new("L", (T, T), 0)
    hd = ImageDraw.Draw(halo)
    hd.ellipse([-T*0.35, -T*0.45, T*0.85, T*0.75], fill=90)
    halo = halo.filter(ImageFilter.GaussianBlur(T*0.16))
    white_layer = Image.new("RGB", (T, T), WHITE)
    tile = Image.composite(white_layer, tile, halo)

    # Vignette sombre en bas (profondeur)
    vig = Image.new("L", (T, T), 0)
    vd = ImageDraw.Draw(vig)
    vd.ellipse([T*0.1, T*0.55, T*0.9, T*1.4], fill=70)
    vig = vig.filter(ImageFilter.GaussianBlur(T*0.18))
    dark_layer = Image.new("RGB", (T, T), darken(base, 0.4))
    tile = Image.composite(dark_layer, tile, vig)

    return tile

# ── Compositer un pictogramme blanc avec ombre portée ──────────────────────────
def stamp(tile, picto_layer):
    # picto_layer : RGBA blanc sur transparent (taille T)
    alpha = picto_layer.split()[3]
    # Ombre : alpha décalée, sombre, floutée
    shadow = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    sh_alpha = alpha.point(lambda a: int(a * 0.38))
    shadow.putalpha(sh_alpha)
    sh_rgb = Image.new("RGB", (T, T), (10, 12, 20))
    shadow = Image.merge("RGBA", (*sh_rgb.split(), sh_alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(T*0.012))
    off = int(T*0.012)
    tile_rgba = tile.convert("RGBA")
    tile_rgba.alpha_composite(shadow, (0, off))
    tile_rgba.alpha_composite(picto_layer)
    return tile_rgba

def new_layer():
    img = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)

# ── Finition : coins arrondis + downscale ──────────────────────────────────────
def finish(tile_rgba, slug):
    mask = Image.new("L", (T, T), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, T-1, T-1], radius=int(T*0.225), fill=255)
    out = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    out.paste(tile_rgba, (0, 0), mask)
    # léger liseré interne clair pour la netteté
    bd = ImageDraw.Draw(out)
    bd.rounded_rectangle([SS, SS, T-1-SS, T-1-SS], radius=int(T*0.225)-SS,
                         outline=(255, 255, 255, 38), width=max(1, SS))
    out = out.resize((N, N), Image.LANCZOS)
    out.save(os.path.join(OUT, f"icon-{slug}.png"), "PNG")
    print(f"✅ icon-{slug}.png")

# ════════════════════════════════════════════════════════════════════════════
# PICTOGRAMMES (dessinés à l'échelle T, centrés)
# ════════════════════════════════════════════════════════════════════════════
CX = CY = T // 2

def picto_securite(base):
    img, d = new_layer()
    w, h = T*0.46, T*0.54
    x0, y0 = CX - w/2, CY - h/2 - T*0.02
    # Bouclier (haut droit, épaules arrondies, pointe basse)
    top = y0
    pts = [
        (CX, top),
        (x0 + w, top + h*0.10),
        (x0 + w, top + h*0.52),
        (CX, top + h),
        (x0, top + h*0.52),
        (x0, top + h*0.10),
    ]
    d.polygon(pts, fill=WHITE)
    # coins hauts adoucis
    rr = w*0.10
    d.ellipse([x0-1, top, x0+2*rr, top+2*rr], fill=WHITE)
    d.ellipse([x0+w-2*rr, top, x0+w+1, top+2*rr], fill=WHITE)
    # Check en négatif (couleur de base)
    cl = darken(base, 0.05)
    lw = int(T*0.045)
    d.line([(CX - w*0.20, CY + h*0.02),
            (CX - w*0.02, CY + h*0.18),
            (CX + w*0.26, CY - h*0.20)],
           fill=cl, width=lw, joint="curve")
    return img

def picto_politique(base):
    # Hôtel de ville : fronton + colonnes + base
    img, d = new_layer()
    w = T*0.52
    x0 = CX - w/2
    yt = CY - T*0.22
    # Fronton (triangle)
    d.polygon([(CX, yt), (x0, yt + T*0.11), (x0 + w, yt + T*0.11)], fill=WHITE)
    # Architrave
    d.rounded_rectangle([x0, yt + T*0.115, x0 + w, yt + T*0.155], radius=T*0.012, fill=WHITE)
    # Colonnes (4)
    cols = 4
    col_w = w*0.10
    gap = (w - cols*col_w) / (cols + 1)
    cy0 = yt + T*0.175
    cy1 = cy0 + T*0.20
    for i in range(cols):
        cx = x0 + gap*(i+1) + col_w*i
        d.rounded_rectangle([cx, cy0, cx + col_w, cy1], radius=col_w*0.3, fill=WHITE)
    # Base / marches
    d.rounded_rectangle([x0 - T*0.02, cy1, x0 + w + T*0.02, cy1 + T*0.045], radius=T*0.012, fill=WHITE)
    d.rounded_rectangle([x0 - T*0.05, cy1 + T*0.05, x0 + w + T*0.05, cy1 + T*0.095], radius=T*0.012, fill=WHITE)
    return img

def picto_education(base):
    # Toque de diplômé (mortarboard) + gland
    img, d = new_layer()
    w = T*0.50
    cy = CY - T*0.06
    # Planche (losange)
    top = [(CX, cy - T*0.14), (CX + w/2, cy), (CX, cy + T*0.14), (CX - w/2, cy)]
    d.polygon(top, fill=WHITE)
    # Calotte (trapèze sous le centre)
    cap_w = w*0.42
    d.polygon([(CX - cap_w/2, cy + T*0.04),
               (CX + cap_w/2, cy + T*0.04),
               (CX + cap_w*0.38, cy + T*0.17),
               (CX - cap_w*0.38, cy + T*0.17)], fill=WHITE)
    # arrondi bas de calotte
    d.ellipse([CX - cap_w*0.38, cy + T*0.155, CX + cap_w*0.38, cy + T*0.195], fill=WHITE)
    # Gland : fil + pampille
    fx = CX + w*0.40
    d.line([(CX + T*0.005, cy), (fx, cy + T*0.02), (fx, cy + T*0.16)], fill=WHITE, width=int(T*0.014), joint="curve")
    d.ellipse([fx - T*0.028, cy + T*0.15, fx + T*0.028, cy + T*0.21], fill=WHITE)
    return img

def picto_sante(base):
    # Croix médicale arrondie
    img, d = new_layer()
    arm = T*0.30
    bar = T*0.115
    r = bar*0.42
    d.rounded_rectangle([CX - bar, CY - arm, CX + bar, CY + arm], radius=r, fill=WHITE)
    d.rounded_rectangle([CX - arm, CY - bar, CX + arm, CY + bar], radius=r, fill=WHITE)
    return img

def picto_cadredevie(base):
    # Feuille (forme pointue) + nervures, dessinées ensemble puis tournées
    leaf, ld = new_layer()
    w, h = T*0.33, T*0.54
    pts = []
    steps = 48
    for i in range(steps+1):
        t = i/steps
        y = -h/2 + h*t
        x = w/2 * math.sin(math.pi * t)
        pts.append((CX + x, CY + y))
    for i in range(steps+1):
        t = 1 - i/steps
        y = -h/2 + h*t
        x = w/2 * math.sin(math.pi * t)
        pts.append((CX - x, CY + y))
    ld.polygon(pts, fill=WHITE)
    # Nervures en couleur de base (verticales, dans la feuille)
    cl = darken(base, 0.07)
    vw = int(T*0.016)
    top_y, bot_y = CY - h*0.42, CY + h*0.42
    ld.line([(CX, top_y), (CX, bot_y)], fill=cl, width=vw, joint="curve")
    # nervures secondaires
    for sy, sl in [(-0.22, 0.13), (-0.02, 0.16), (0.18, 0.12)]:
        yy = CY + h*sy
        ld.line([(CX, yy), (CX + w*sl, yy - h*0.10)], fill=cl, width=int(vw*0.7))
        ld.line([(CX, yy), (CX - w*sl, yy - h*0.10)], fill=cl, width=int(vw*0.7))
    # petite tige en bas
    ld.line([(CX, bot_y), (CX, bot_y + h*0.10)], fill=WHITE, width=int(T*0.018))
    leaf = leaf.rotate(-30, resample=Image.BICUBIC, center=(CX, CY))
    return leaf

def picto_gpseo(base):
    # Réseau de communes : noeud central + 3 noeuds reliés (intercommunalité)
    img, d = new_layer()
    R = T*0.22
    rc = T*0.052   # rayon noeud central
    rn = T*0.044   # rayon noeuds
    nodes = []
    for k in range(3):
        a = -math.pi/2 + k*2*math.pi/3
        nodes.append((CX + R*math.cos(a), CY + R*math.sin(a)))
    # liens
    lw = int(T*0.022)
    for nx, ny in nodes:
        d.line([(CX, CY), (nx, ny)], fill=WHITE, width=lw)
    # liens périphériques (triangle léger)
    for i in range(3):
        x1, y1 = nodes[i]
        x2, y2 = nodes[(i+1) % 3]
        d.line([(x1, y1), (x2, y2)], fill=(255,255,255,150), width=int(lw*0.7))
    # noeuds
    for nx, ny in nodes:
        d.ellipse([nx-rn, ny-rn, nx+rn, ny+rn], fill=WHITE)
    d.ellipse([CX-rc, CY-rc, CX+rc, CY+rc], fill=WHITE)
    # petit point coloré au centre pour la lisibilité
    cl = darken(base, 0.1)
    d.ellipse([CX-rc*0.4, CY-rc*0.4, CX+rc*0.4, CY+rc*0.4], fill=cl)
    return img

# ════════════════════════════════════════════════════════════════════════════
CATS = [
    ("securite",   (220, 38,  38),  picto_securite),
    ("politique",  (124, 58,  237), picto_politique),
    ("education",  (5,   150, 105), picto_education),
    ("sante",      (3,   105, 161), picto_sante),
    ("cadredevie", (217, 119, 6),   picto_cadredevie),
    ("gpseo",      (91,  33,  182), picto_gpseo),
]

for slug, base, fn in CATS:
    tile = make_tile(base)
    picto = fn(base)
    composed = stamp(tile, picto)
    finish(composed, slug)

print("\n🎨 Icônes premium générées.")
