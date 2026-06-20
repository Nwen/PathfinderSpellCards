"""Parser du dump XML pathfinder-fr.org.

Format XML attendu (sérialisation C# XmlSerializer de XmlWikiPage) :

    <wikiPage version="N">
      <title>Pathfinder-RPG.Boule de feu</title>
      <fullName>Pathfinder-RPG.Boule de feu</fullName>
      <raw>'''École''' [[évocation]] …</raw>
      <body><!-- HTML rendu --></body>
      <categories><category>Sort</category></categories>
    </wikiPage>

Les `<br/>` dans <raw> servent de séparateurs de lignes.
"""
from __future__ import annotations

import html
import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterator

log = logging.getLogger(__name__)

# ── Séquence de fin de ligne dans le markup brut ─────────────────────────────
_EOL = r"(?:\n|<br\s*/?>)"

# ── Patterns de champs ────────────────────────────────────────────────────────
SCHOOL_RE = re.compile(
    r"'''[ÉEée]cole'''\s+"
    r"(?:"
    r"\[\[[^\]|#]*(?:#[^\]|]*)?\|([^\]]+)\]\]"  # group 1: [[any|DISPLAY]]
    r"|\[\[([^\]|#]+)(?:#[^\]|]+)?\]\]"           # group 2: [[LINK]]
    r"|(Universel(?:le)?)"                         # group 3: Universel(le)
    r")",
    re.IGNORECASE,
)

DESCRIPTOR_RE = re.compile(
    r"\[\[(?:registre|Présentation des sorts#registre)\|([^\]]+)\]\]",
    re.IGNORECASE,
)

SUBSCHOOL_RE = re.compile(
    r"\(\[\[(?:branche [^\]]+|[^\]]+)\|([^\]]+)\]\]\)",
    re.IGNORECASE,
)

LEVEL_RE = re.compile(
    r"'''Niveau'''\s+(.+?)(?:" + _EOL + r"|$)",
    re.IGNORECASE,
)

CASTING_TIME_RE = re.compile(
    r"'''Temps d[''’]incantation'''\s+(.+?)(?:" + _EOL + r"|$)",
    re.IGNORECASE,
)

COMPONENTS_RE = re.compile(
    r"'''Composantes?'''\s+"
    r"(?:\[\[[^\]|]*\|)?([VGMFSvgmfs](?:[,\s/]+[VGMFSvgmfs])*)(?:\]\])?",
    re.IGNORECASE,
)

RANGE_RE = re.compile(
    r"'''Portée'''\s+(.+?)(?:" + _EOL + r"|$)",
    re.IGNORECASE,
)

TARGET_RE = re.compile(
    r"'''(?:Cibles?|Effet|Zone d[''’]effet|Zone"
    r"|Cible ou zone d[''’]effet|Cibles? ou effet"
    r"|Cible et zone d[''’]effet|Cible ou effet"
    r"|Zone d[''’]effet ou cible|Cible, effet ou zone d[''’]effet"
    r")'''\s+(.+?)(?:" + _EOL + r"|$)",
    re.IGNORECASE,
)

DURATION_RE = re.compile(
    r"'''Dur[ée]e'''\s+(.+?)(?:" + _EOL + r"|$)",
    re.IGNORECASE,
)

SAVING_THROW_RE = re.compile(
    r"'''Jet de sauvegarde'''\s+(.+?)(?:;|" + _EOL + r"|$)",
    re.IGNORECASE,
)

SR_RE = re.compile(
    r"'''(?:R[ée]sistance [àa] la magie|RM)'''\s+(.+?)(?:" + _EOL + r"|$)",
    re.IGNORECASE,
)

# {s:c} et {s:cs} sont des marqueurs de mise en page, pas des sources — on exige une majuscule initiale
SOURCE_RE = re.compile(r"\{s:([A-Z][A-Za-z0-9]*)\}")

# Dernier champ de métadonnées — pour détecter où commence la description
_LAST_FIELD_RE = re.compile(
    r"'''(?:R[ée]sistance [àa] la magie|RM|Jet de sauvegarde"
    r"|Dur[ée]e|Cibles?|Effet|Zone d[''’]effet|Zone"
    r"|Port[ée]e|Composantes?|Temps d[''’]incantation|Niveau|[ÉEée]cole)'''",
    re.IGNORECASE,
)

# ── Tables de normalisation ───────────────────────────────────────────────────
_SCHOOL_MAP: dict[str, str] = {
    "abjuration": "abjuration",
    "divination": "divination",
    "enchantement": "enchantement",
    "evocation": "évocation",
    "évocation": "évocation",
    "illusion": "illusion",
    "invocation": "invocation",
    "conjuration": "invocation",
    "necromancie": "nécromancie",
    "nécromancie": "nécromancie",
    "transmutation": "transmutation",
    "universel": "universel",
    "universelle": "universel",
}

_CLASS_MAP: dict[str, str] = {
    # ── Livre de base / APG ───────────────────────────────────────────────────
    "barde": "barde",
    "ensorceleur": "ensorceleur",
    "magicien": "magicien",
    "prêtre": "prêtre",
    "pretre": "prêtre",
    "clerc": "prêtre",
    "druide": "druide",
    "paladin": "paladin",
    "rôdeur": "rôdeur",
    "rodeur": "rôdeur",
    "alchimiste": "alchimiste",
    "inquisiteur": "inquisiteur",
    "invocateur": "invocateur",
    "conjurateur": "invocateur",
    "sorcière": "sorcière",
    "sorciere": "sorcière",
    "oracle": "oracle",
    "magus": "magus",
    "antipaladin": "antipaladin",
    # ── Advanced Class Guide (ACG) ────────────────────────────────────────────
    "arcaniste": "arcaniste",
    "chaman": "chaman",
    "chasseur": "chasseur",
    "skald": "skald",
    "sanguin": "sanguin",
    "prêtre combattant": "prêtre combattant",
    "pretre combattant": "prêtre combattant",
    "investigateur": "investigateur",
    # ── Occult Adventures (OA) ────────────────────────────────────────────────
    "psychiste": "psychiste",
    "occultiste": "occultiste",
    "médium": "médium",
    "medium": "médium",
    "mesmériste": "mesmériste",
    "mesmeriste": "mesmériste",
    "spirite": "spirite",
}


# ── Modèle de données ─────────────────────────────────────────────────────────
@dataclass
class SpellData:
    title: str
    name_fr: str
    slug_fr: str
    school: str
    subschool: str | None
    descriptors: str | None
    level_json: dict[str, int]
    casting_time: str | None
    components: str | None
    spell_range: str | None
    target: str | None
    area: str | None
    duration: str | None
    saving_throw: str | None
    spell_resistance: str | None
    description_fr: str
    source: str | None
    raw_url: str | None
    is_ogl: bool = True


# ── Point d'entrée public ─────────────────────────────────────────────────────
def parse_dump(xml_path: str) -> list[SpellData]:
    """Parse le dump XML (répertoire ou fichier unique) et retourne la liste des sorts."""
    from pathlib import Path as _Path
    p = _Path(xml_path)
    if p.is_dir():
        return _parse_directory(p)

    log.info("Parsing XML (fichier unique) : %s", xml_path)
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as exc:
        log.error("Échec parsing XML : %s", exc)
        raise

    root = tree.getroot()
    if root.tag in ("wikiPage", "XmlWikiPage"):
        return _parse_page_element(root)

    spells: list[SpellData] = []
    for page in _iter_pages(root):
        title = _get_field(page, "title", "Title", "name") or ""
        raw = _get_field(page, "raw", "Raw", "text")
        full_name = _get_field(page, "fullName", "FullName")
        if not raw or not _is_spell(raw):
            continue
        spells.extend(_parse_raw(title, raw, full_name))

    log.info("Sorts parsés : %d", len(spells))
    return spells


def _parse_directory(dir_path: "Path") -> list[SpellData]:
    """Itère sur les fichiers XML individuels du répertoire (format dump actuel)."""
    xml_files = list(dir_path.glob("*.xml"))
    total = len(xml_files)
    log.info("Parsing répertoire : %s (%d fichiers)", dir_path, total)

    spells: list[SpellData] = []

    for i, xml_file in enumerate(xml_files):
        if i % 2000 == 0 and i > 0:
            log.info("  %d/%d fichiers traités, %d sorts trouvés …", i, total, len(spells))
        try:
            tree = ET.parse(xml_file)
        except ET.ParseError:
            continue
        root = tree.getroot()
        spells.extend(_parse_page_element(root))

    log.info("Sorts parsés : %d (sur %d fichiers)", len(spells), total)
    return spells


def _parse_page_element(root: ET.Element) -> list[SpellData]:
    """Parse un élément <wikiPage> racine et retourne 0 ou 1 SpellData."""
    # Pré-filtre rapide via les catégories : accepte tout ce qui contient le mot "sort"
    # (avec frontière de mot) pour couvrir "Sort", "Sort psychique", "Pathfinder-RPG.Sort…"
    categories = root.find("categories")
    if categories is not None:
        cat_texts = [c.text or "" for c in categories.findall("category")]
        if cat_texts and not any(
            re.search(r"\bsort\b", t, re.IGNORECASE) for t in cat_texts
        ):
            return []

    title_el = root.find("title")
    title = (title_el.text or "").strip() if title_el is not None else ""

    raw_el = root.find("raw")
    raw = (raw_el.text or "").strip() if raw_el is not None else ""

    if not raw or not _is_spell(raw):
        return []

    full_name = f"Pathfinder-RPG.{title}"
    return _parse_raw(title, raw, full_name)


# ── Helpers XML ───────────────────────────────────────────────────────────────
def _iter_pages(root: ET.Element) -> Iterator[ET.Element]:
    """Itère sur les éléments page quel que soit le format XML."""
    for tag in ("wikiPage", "XmlWikiPage", "page", "Page", "item"):
        pages = root.findall(".//" + tag)
        if pages:
            log.debug("Format XML : <%s>, %d pages trouvées", tag, len(pages))
            return iter(pages)

    children = list(root)
    if children:
        log.debug("Fallback : %d enfants directs de <%s>", len(children), root.tag)
        return iter(children)

    return iter([])


def _get_field(element: ET.Element, *names: str) -> str | None:
    """Récupère le contenu texte d'un élément enfant (essaie plusieurs noms)."""
    for name in names:
        child = element.find(name)
        if child is not None:
            return _element_text(child)
    return None


def _element_text(el: ET.Element) -> str:
    """Sérialise le contenu d'un élément XML en texte brut.

    Convertit les <br/> en sauts de ligne, supprime les balises restantes,
    et décode les entités HTML.
    """
    raw = ET.tostring(el, encoding="unicode")
    # Supprime la balise racine
    raw = re.sub(r"^<[^>]+>", "", raw)
    raw = re.sub(r"</[^>]+>$", "", raw)
    # Décode d'abord les entités (gère &lt;br/&gt; → <br/>)
    raw = html.unescape(raw)
    # Convertit les <br> en sauts de ligne
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    # Supprime les balises restantes
    raw = re.sub(r"<[^>]+>", "", raw)
    return raw.strip()


# ── Détection de sort ─────────────────────────────────────────────────────────
def _is_spell(raw: str) -> bool:
    """Vrai si le markup brut ressemble à une page de sort."""
    return bool(re.search(r"'''[ÉEée]cole'''", raw, re.IGNORECASE))


# ── Parsing d'un sort ─────────────────────────────────────────────────────────
def _parse_spell(title: str, raw: str, full_name: str | None) -> SpellData | None:
    name_fr = _clean_title(title)
    slug_fr = _slugify(name_fr)

    school, subschool, descriptors = _parse_school(raw)
    if not school:
        return None

    levels = _parse_levels(raw)
    casting_time = _extract(CASTING_TIME_RE, raw)
    components = _extract(COMPONENTS_RE, raw)
    spell_range = _extract(RANGE_RE, raw)
    target_or_area = _extract(TARGET_RE, raw)
    duration = _extract(DURATION_RE, raw)
    saving_throw = _extract(SAVING_THROW_RE, raw)
    spell_resistance = _extract(SR_RE, raw)
    source = _extract_source(raw)
    description = _extract_description(raw)

    raw_url = (
        f"http://www.pathfinder-fr.org/Wiki/{full_name}.ashx" if full_name else None
    )

    return SpellData(
        title=title,
        name_fr=name_fr,
        slug_fr=slug_fr,
        school=school,
        subschool=subschool or None,
        descriptors=", ".join(descriptors) if descriptors else None,
        level_json=levels,
        casting_time=_clean_wiki(casting_time) if casting_time else None,
        components=_clean_wiki(components) if components else None,
        spell_range=_clean_wiki(spell_range) if spell_range else None,
        target=_clean_wiki(target_or_area) if target_or_area else None,
        area=None,
        duration=_clean_wiki(duration) if duration else None,
        saving_throw=_clean_wiki(saving_throw) if saving_throw else None,
        spell_resistance=_clean_wiki(spell_resistance) if spell_resistance else None,
        description_fr=_clean_wiki(description),
        source=source,
        raw_url=raw_url,
        is_ogl=True,
    )


# ── Parsers de champs ─────────────────────────────────────────────────────────
def _clean_title(title: str) -> str:
    """Supprime le préfixe de namespace wiki ('Pathfinder-RPG.')."""
    if "." in title:
        title = title.rsplit(".", 1)[-1]
    return title.strip()


def _slugify(text: str) -> str:
    """Convertit un titre en slug URL (ASCII, tirets)."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def _parse_school(raw: str) -> tuple[str, str, list[str]]:
    """Retourne (école, sous-école, [registres])."""
    m = SCHOOL_RE.search(raw)
    if not m:
        return "", "", []

    school_raw = (m.group(1) or m.group(2) or m.group(3) or "").strip().lower()
    # Normalise les variantes avec accents / sans
    school_raw = unicodedata.normalize("NFKD", school_raw)
    school_raw = school_raw.encode("ascii", "ignore").decode("ascii").lower()
    # Supprime le préfixe "ecole " issu de liens catégorie comme [[Ecole divination]]
    if school_raw.startswith("ecole "):
        school_raw = school_raw[len("ecole "):]
    school = _SCHOOL_MAP.get(school_raw, school_raw)

    # Sous-école ex: ([[branche invocation|création]])
    window = raw[m.start() : m.start() + 300]
    sub_m = SUBSCHOOL_RE.search(window)
    subschool = sub_m.group(1).strip() if sub_m else ""

    # Registres/descripteurs ex: [[registre|feu]]
    descriptors = DESCRIPTOR_RE.findall(raw[:800])

    return school, subschool, descriptors


def _parse_levels(raw: str) -> dict[str, int]:
    """Extrait le mapping classe → niveau depuis la ligne '''Niveau'''."""
    m = LEVEL_RE.search(raw)
    if not m:
        return {}

    level_line = m.group(1)
    levels: dict[str, int] = {}

    # Pattern 1 : [[class1|x]]/[[class2|y]] N  (ensorceleur/magicien)
    for cm in re.finditer(
        r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]\s*/\s*\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]\s*(\d+)",
        level_line,
    ):
        for grp in (1, 2):
            cls = _CLASS_MAP.get(cm.group(grp).strip().lower(), cm.group(grp).strip().lower())
            levels[cls] = int(cm.group(3))

    # Pattern 2 : [[class|x]] N  (classe unique)
    for cm in re.finditer(
        r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]\s*(\d+)",
        level_line,
    ):
        cls_raw = cm.group(1).strip().lower()
        cls = _CLASS_MAP.get(cls_raw, cls_raw)
        if cls not in levels:  # ne pas écraser ce que pattern 1 a déjà trouvé
            levels[cls] = int(cm.group(2))

    return levels


def _extract(pattern: re.Pattern[str], raw: str) -> str | None:
    m = pattern.search(raw)
    return m.group(1).strip() if m else None


def _extract_source(raw: str) -> str | None:
    m = SOURCE_RE.search(raw)
    return m.group(1).upper() if m else None


_SUB_SPELL_START = re.compile(r"\n\(\(\(|\n==[^=]")

# Blocs de sous-sorts inline : (((Nom du sort\ncontent\n)))
_SUB_SPELL_BLOCK_RE = re.compile(r"\(\(\(([^\n]+)\n(.*?)\)\)\)", re.DOTALL)
# Sections ==Titre== dans une page multi-sorts
_SECTION_RE = re.compile(r"\n==([^=][^=]*?)==[ \t]*\n")


def _extract_description(raw: str) -> str:
    """Extrait la description principale, avant les variantes embarquées."""
    # Tronque avant les macros de sous-sorts ((( ou sections de niveau 2 ==Titre==
    stop = _SUB_SPELL_START.search(raw)
    body = raw[: stop.start()] if stop else raw

    last_end = 0
    for m in _LAST_FIELD_RE.finditer(body):
        eol = body.find("\n", m.end())
        last_end = max(last_end, eol if eol != -1 else len(body))

    if last_end == 0:
        return body
    return body[last_end:].strip()


# ── Parsers multi-sorts (pages avec variantes) ───────────────────────────────

def _try_sub_spell_blocks(title: str, raw: str, full_name: str | None) -> list[SpellData]:
    """Extrait les sous-sorts depuis des blocs (((Nom\ncontent\n))) dans une page."""
    results: list[SpellData] = []
    for m in _SUB_SPELL_BLOCK_RE.finditer(raw):
        sub_name = m.group(1).strip()
        sub_raw = m.group(2)
        if not _is_spell(sub_raw):
            continue
        try:
            spell = _parse_spell(sub_name, sub_raw, full_name)
            if spell:
                results.append(spell)
        except Exception as exc:
            log.debug("Erreur parsing sous-sort '%s' dans '%s' : %s", sub_name, title, exc)
    return results


def _try_sections(title: str, raw: str, full_name: str | None) -> list[SpellData]:
    """Extrait les sous-sorts depuis des sections ==Titre== dans une page."""
    matches = list(_SECTION_RE.finditer(raw))
    if not matches:
        return []
    results: list[SpellData] = []
    for i, m in enumerate(matches):
        section_name = re.sub(r"\s*[\(:].*", "", m.group(1)).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        section_raw = raw[start:end]
        if not _is_spell(section_raw):
            continue
        try:
            spell = _parse_spell(section_name, section_raw, full_name)
            if spell:
                results.append(spell)
        except Exception as exc:
            log.debug("Erreur parsing section '%s' dans '%s' : %s", section_name, title, exc)
    return results


def _parse_raw(title: str, raw: str, full_name: str | None) -> list[SpellData]:
    """Parse le contenu brut d'une page ; retourne 0, 1 ou plusieurs sorts."""
    results = _try_sub_spell_blocks(title, raw, full_name)
    if results:
        return results
    results = _try_sections(title, raw, full_name)
    if results:
        return results
    try:
        spell = _parse_spell(title, raw, full_name)
        return [spell] if spell else []
    except Exception as exc:
        log.debug("Erreur parsing '%s' : %s", title, exc)
        return []


# ── Nettoyage du markup wiki ──────────────────────────────────────────────────
_LINK_WITH_DISPLAY = re.compile(r"\[\[[^\]|#]*(?:#[^\]|]*)?\|([^\]]+)\]\]")
_LINK_PLAIN = re.compile(r"\[\[([^\]]+)\]\]")
_BOLD_ITALIC = re.compile(r"'{2,3}")
_SOURCE_MARKER = re.compile(r"\{s:[A-Za-z0-9]+\}", re.IGNORECASE)
_SQUARE_MARKER = re.compile(r"\{s:c\}", re.IGNORECASE)
_EXTRA_SPACES = re.compile(r" {2,}")
_EXTRA_NEWLINES = re.compile(r"\n{3,}")
# Blocs FAQ : {s:FAQ|...} — le contenu peut contenir des {s:XX} imbriqués (un niveau)
_FAQ_BLOCK = re.compile(r"\{s:FAQ\|(?:[^{}]|\{[^{}]*\})*\}", re.DOTALL | re.IGNORECASE)
# Tableaux wiki : {|...|} — traités en dernier, après nettoyage du contenu des cellules
_WIKI_TABLE_RE = re.compile(r"\{\|.*?\|\}", re.DOTALL)


def _wiki_table_to_html(m: re.Match) -> str:
    """Convertit un tableau wiki {|...|} en <table class="wiki-table"> HTML."""
    lines = m.group(0).splitlines()
    rows: list[list[str]] = []
    cur: list[str] = []
    is_header_row = False

    for line in lines:
        s = line.strip()
        if not s or s.startswith("{|") or s.startswith("|+"):
            continue
        if s.startswith("|}"):
            if cur:
                rows.append(cur)
            break
        if s.startswith("|-"):
            if cur:
                rows.append(cur)
                cur = []
            cls_lower = s.lower()
            is_header_row = "titre" in cls_lower or "soustitre" in cls_lower
            continue
        if s.startswith("!") or s.startswith("|"):
            is_th = s.startswith("!")
            sep = "!!" if is_th else "||"
            for raw in s[1:].split(sep):
                raw = raw.strip()
                attrs: dict[str, str] = {}
                if "|" in raw:
                    attr_part, content = raw.split("|", 1)
                    content = content.strip()
                    for am in re.finditer(r"(?i)(rowspan|colspan)=[\"']?(\d+)[\"']?", attr_part):
                        attrs[am.group(1).lower()] = am.group(2)
                else:
                    content = raw
                tag = "th" if (is_th or is_header_row) else "td"
                attr_str = "".join(f' {k}="{v}"' for k, v in attrs.items())
                cur.append(f"<{tag}{attr_str}>{content}</{tag}>")

    if cur:
        rows.append(cur)
    if not rows:
        return ""

    parts = ["<table class=\"wiki-table\">"]
    for row in rows:
        parts.append("<tr>" + "".join(row) + "</tr>")
    parts.append("</table>")
    return "".join(parts)


def _clean_wiki(text: str) -> str:
    """Supprime le markup wiki et retourne du texte lisible (avec HTML pour les tableaux)."""
    if not text:
        return ""
    text = _FAQ_BLOCK.sub("", text)  # doit précéder les autres substitutions
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = _LINK_WITH_DISPLAY.sub(r"\1", text)
    text = _LINK_PLAIN.sub(r"\1", text)
    text = _BOLD_ITALIC.sub("", text)
    text = _SQUARE_MARKER.sub("c", text)  # doit précéder _SOURCE_MARKER
    text = _SOURCE_MARKER.sub("", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = _EXTRA_SPACES.sub(" ", text)
    text = _EXTRA_NEWLINES.sub("\n\n", text)
    # Tableaux wiki en dernier : le contenu des cellules a déjà été nettoyé
    text = _WIKI_TABLE_RE.sub(_wiki_table_to_html, text)
    return text.strip()
