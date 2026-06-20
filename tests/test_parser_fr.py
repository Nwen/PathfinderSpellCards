"""Tests unitaires du parser pathfinder-fr."""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET

import pytest

from src.ingest.parser_fr import (
    _clean_wiki,
    _is_spell,
    _parse_page_element,
    _parse_school,
    _parse_levels,
    _slugify,
    parse_dump,
)

# ── Fixtures de markup ────────────────────────────────────────────────────────

FIREBALL_RAW = """\
'''École''' [[évocation]] ([[registre|feu]])
'''Niveau''' [[ensorceleur|Ens]]/[[magicien|Mag]] 3, [[barde|Bar]] 3
'''Temps d'incantation''' 1 [[action simple]]
'''Composantes''' [[COMPOSANTES|V, G]]
'''Portée''' longue (120 m + 12 m/[[niveau]])
'''Zone d'effet''' boule de feu de 6 m de rayon
'''Durée''' instantanée
'''Jet de sauvegarde''' [[Présentation des sorts#jetsdesauvegarde|Réflexes]], 1/2 dégâts
'''Résistance à la magie''' oui

Une boule de feu jaillit du bout du doigt du personnage.
Elle explose au point désigné et inflige 1d6 points de dégâts de feu par niveau.
"""

WISH_RAW = """\
'''École''' Universel
'''Niveau''' [[ensorceleur|Ens]]/[[magicien|Mag]] 9
'''Temps d'incantation''' 1 [[action simple]]
'''Composantes''' [[COMPOSANTES|V]]
'''Portée''' illimitée
'''Cibles''' voir description
'''Durée''' voir description
'''Jet de sauvegarde''' aucun, voir description
'''Résistance à la magie''' oui, voir description

Souhait est le sort le plus puissant et le plus polyvalent disponible pour un lanceur de sorts.
"""

CHARM_RAW = """\
'''École''' [[enchantement]] ([[branche enchantement|charme]]) [[registre|mental]]
'''Niveau''' [[barde|Bar]] 1, [[ensorceleur|Ens]]/[[magicien|Mag]] 1
'''Temps d'incantation''' 1 [[action simple]]
'''Composantes''' [[COMPOSANTES|V, G]]
'''Portée''' courte (7,50 m + 1,50 m/2 [[niveau|niveaux]])
'''Cibles''' un humanoïde
'''Durée''' 1 heure/niveau
'''Jet de sauvegarde''' [[Présentation des sorts#jetsdesauvegarde|Volonté]] pour annuler
'''Résistance à la magie''' oui

La cible considère le lanceur de sorts comme son ami.
"""

NON_SPELL_RAW = """\
== Description ==
Ce monstre est très dangereux.
Il attaque avec ses griffes pour 2d6 dégâts.
"""

# Bug de régression : certains liens wiki utilisent [[Ecole divination]] ou
# [[Ecole divination|divination]] au lieu de [[divination]].
PSYCHIC_RAW = """\
'''École''' [[enchantement]] ([[registre|émotion]], [[registre|mental]])
'''Niveau''' [[psychiste|Psy]] 1, [[mesmériste|Mes]] 1
'''Temps d'incantation''' 1 [[action simple]]
'''Composantes''' [[COMPOSANTES|V]]
'''Portée''' courte (7,50 m + 1,50 m/2 niveaux)
'''Cibles''' 1 créature
'''Durée''' instantanée
'''Jet de sauvegarde''' Volonté annule
'''Résistance à la magie''' oui

Sort de psychiste test.
"""

ECOLE_PREFIXED_BARE_RAW = """\
'''École''' [[Ecole divination]]
'''Niveau''' [[prêtre|Prê]] 2
'''Temps d'incantation''' 1 [[action simple]]
'''Composantes''' [[COMPOSANTES|V, G]]
'''Portée''' courte (7,50 m + 1,50 m/2 niveaux)
'''Cibles''' 1 créature
'''Durée''' 1 minute/niveau
'''Jet de sauvegarde''' aucun
'''Résistance à la magie''' oui

Sort de divination test (lien catégorie sans texte d'affichage).
"""

ECOLE_PREFIXED_DISPLAY_RAW = """\
'''École''' [[Ecole divination|divination]]
'''Niveau''' [[prêtre|Prê]] 3
'''Temps d'incantation''' 1 [[action simple]]
'''Composantes''' [[COMPOSANTES|V, G, F]]
'''Portée''' courte
'''Cibles''' 1 créature
'''Durée''' instantanée
'''Jet de sauvegarde''' Volonté annule
'''Résistance à la magie''' oui

Sort de divination test (lien catégorie avec texte d'affichage).
"""

# ── Helpers XML pour tests de parse_dump ─────────────────────────────────────

def _make_xml(pages: list[tuple[str, str, str]]) -> str:
    """Crée un mini XML de dump avec les pages données (title, fullName, raw)."""
    root = ET.Element("root")
    for title, full_name, raw in pages:
        page = ET.SubElement(root, "wikiPage")
        ET.SubElement(page, "title").text = title
        ET.SubElement(page, "fullName").text = full_name
        ET.SubElement(page, "raw").text = raw
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _parse_xml_string(xml_str: str):
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml_str)
        path = f.name
    try:
        return parse_dump(path)
    finally:
        os.unlink(path)


# ── Tests : slugify ───────────────────────────────────────────────────────────

class TestSlugify:
    def test_basic(self):
        assert _slugify("Boule de feu") == "boule-de-feu"

    def test_accent(self):
        assert _slugify("Soins légers") == "soins-legers"

    def test_hyphen_preserved(self):
        assert _slugify("Charme-personne") == "charme-personne"

    def test_multiple_spaces(self):
        assert _slugify("Dissipation de la magie") == "dissipation-de-la-magie"

    def test_wish(self):
        assert _slugify("Souhait") == "souhait"


# ── Tests : détection de sort ─────────────────────────────────────────────────

class TestIsSpell:
    def test_fireball_detected(self):
        assert _is_spell(FIREBALL_RAW)

    def test_wish_detected(self):
        assert _is_spell(WISH_RAW)

    def test_non_spell_rejected(self):
        assert not _is_spell(NON_SPELL_RAW)

    def test_empty_rejected(self):
        assert not _is_spell("")


# ── Tests : école ─────────────────────────────────────────────────────────────

class TestParseSchool:
    def test_evocation_with_descriptor(self):
        school, _, descriptors = _parse_school(FIREBALL_RAW)
        assert school == "évocation"
        assert "feu" in descriptors

    def test_universal(self):
        school, _, _ = _parse_school(WISH_RAW)
        assert school == "universel"

    def test_enchantement_with_subschool(self):
        school, _, descriptors = _parse_school(CHARM_RAW)
        assert school == "enchantement"
        assert "mental" in descriptors

    def test_no_school_returns_empty(self):
        school, _, _ = _parse_school(NON_SPELL_RAW)
        assert school == ""

    def test_ecole_prefixed_bare_link(self):
        # Régression : [[Ecole divination]] doit donner "divination", pas "ecole divination"
        school, _, _ = _parse_school(ECOLE_PREFIXED_BARE_RAW)
        assert school == "divination"

    def test_ecole_prefixed_display_link(self):
        # Régression : [[Ecole divination|divination]] doit donner "divination"
        school, _, _ = _parse_school(ECOLE_PREFIXED_DISPLAY_RAW)
        assert school == "divination"


# ── Tests : niveaux ───────────────────────────────────────────────────────────

class TestParseLevels:
    def test_fireball_ens_mag_barde(self):
        levels = _parse_levels(FIREBALL_RAW)
        assert levels.get("ensorceleur") == 3
        assert levels.get("magicien") == 3
        assert levels.get("barde") == 3

    def test_wish_level_9(self):
        levels = _parse_levels(WISH_RAW)
        assert levels.get("ensorceleur") == 9
        assert levels.get("magicien") == 9

    def test_charm_multi_class(self):
        levels = _parse_levels(CHARM_RAW)
        assert levels.get("barde") == 1
        assert levels.get("ensorceleur") == 1
        assert levels.get("magicien") == 1

    def test_no_level_line(self):
        levels = _parse_levels(NON_SPELL_RAW)
        assert levels == {}


# ── Tests : nettoyage wiki ────────────────────────────────────────────────────

class TestCleanWiki:
    def test_removes_link_with_display(self):
        result = _clean_wiki("1 [[action simple|action simple]]")
        assert "action simple" in result
        assert "[[" not in result

    def test_removes_link_plain(self):
        result = _clean_wiki("[[évocation]]")
        assert "évocation" in result
        assert "[[" not in result

    def test_removes_bold(self):
        result = _clean_wiki("'''École'''")
        assert "École" in result
        assert "'''" not in result

    def test_removes_source_marker(self):
        result = _clean_wiki("Texte {s:APG} suite")
        assert "{s:" not in result
        assert "Texte" in result
        assert "suite" in result

    def test_br_becomes_newline(self):
        result = _clean_wiki("ligne 1<br/>ligne 2")
        assert "\n" in result

    def test_empty_string(self):
        assert _clean_wiki("") == ""

    def test_removes_faq_block(self):
        text = "Description normale. {s:FAQ|Question ? Réponse.} Suite."
        result = _clean_wiki(text)
        assert "{s:FAQ" not in result
        assert "Question" not in result
        assert "Réponse" not in result
        assert "Description normale." in result

    def test_removes_multiline_faq_block(self):
        faq = "{s:FAQ|→ Q1 ?\n\nRép1.\n\n→ Q2 ?\n\nRép2.}"
        result = _clean_wiki("Description. " + faq)
        assert "Q1" not in result
        assert "Rép1" not in result
        assert "Description." in result

    def test_removes_faq_block_with_nested_source_marker(self):
        # {s:APG} imbriqué dans un bloc FAQ ne doit pas casser l'extraction
        faq = "{s:FAQ|Voir {s:APG} pour les détails.}"
        result = _clean_wiki("Description. " + faq)
        assert "Voir" not in result
        assert "Description." in result

    def test_wiki_table_converted_to_html(self):
        table = """\
{| CLASS="tablo"
|-
| Cellule A || Cellule B
|-
| Cellule C || Cellule D
|}"""
        result = _clean_wiki("Avant.\n" + table + "\nAprès.")
        assert "<table" in result
        assert "Cellule A" in result
        assert "Cellule B" in result
        assert "{|" not in result

    def test_wiki_table_header_rows_use_th(self):
        table = """\
{| CLASS="tablo"
|- CLASS="titre"
| Col1 || Col2
|-
| Val1 || Val2
|}"""
        result = _clean_wiki(table)
        assert "<th>" in result
        assert "<td>" in result

    def test_wiki_table_cell_attributes(self):
        table = """\
{| CLASS="tablo"
|-
| ROWSPAN="2" | Cellule fusionnée || Simple
|}"""
        result = _clean_wiki(table)
        assert 'rowspan="2"' in result
        assert "Cellule fusionnée" in result

    def test_wiki_table_links_in_cells_cleaned(self):
        table = """\
{| CLASS="tablo"
|-
| [[évocation]] || [[Présentation des sorts#aura|Aura faible]]
|}"""
        result = _clean_wiki(table)
        assert "évocation" in result
        assert "Aura faible" in result
        assert "[[" not in result


# ── Tests : filtre catégories ────────────────────────────────────────────────

class TestCategoryFilter:
    """Teste _parse_page_element avec différents formats de catégories."""

    def _page(self, title: str, raw: str, categories: list[str] | None = None):
        root = ET.Element("wikiPage")
        ET.SubElement(root, "title").text = title
        ET.SubElement(root, "fullName").text = title
        ET.SubElement(root, "raw").text = raw
        if categories is not None:
            cats_el = ET.SubElement(root, "categories")
            for c in categories:
                ET.SubElement(cats_el, "category").text = c
        return root

    def test_bare_sort_category_passes(self):
        # "Sort" sans préfixe — était rejeté avec l'ancien filtre ".Sort"
        page = self._page("Pathfinder-RPG.Boule de feu", FIREBALL_RAW, ["Sort"])
        assert len(_parse_page_element(page)) == 1

    def test_sort_psychique_category_passes(self):
        page = self._page("Pathfinder-RPG.Boule de feu", FIREBALL_RAW, ["Sort psychique"])
        assert len(_parse_page_element(page)) == 1

    def test_namespaced_sort_category_passes(self):
        page = self._page("Pathfinder-RPG.Boule de feu", FIREBALL_RAW, ["Pathfinder-RPG.Sort"])
        assert len(_parse_page_element(page)) == 1

    def test_non_spell_category_filtered(self):
        # Une page sans aucune catégorie "sort" est rejetée
        page = self._page("Pathfinder-RPG.Monstre", NON_SPELL_RAW, ["Monstre", "PNJ"])
        assert len(_parse_page_element(page)) == 0

    def test_no_categories_element_passes(self):
        # Pas d'élément <categories> → le filtre est ignoré
        page = self._page("Pathfinder-RPG.Boule de feu", FIREBALL_RAW)
        assert len(_parse_page_element(page)) == 1


# ── Tests : classes Occult Adventures ────────────────────────────────────────

class TestPsychicClasses:
    def test_psychic_levels_stored(self):
        levels = _parse_levels(PSYCHIC_RAW)
        assert levels.get("psychiste") == 1
        assert levels.get("mesmériste") == 1

    def test_psychic_school_parsed(self):
        school, _, _ = _parse_school(PSYCHIC_RAW)
        assert school == "enchantement"

    def test_psychic_spell_in_dump(self):
        xml = _make_xml([("Pathfinder-RPG.Coup mental I", "Pathfinder-RPG.Coup mental I", PSYCHIC_RAW)])
        spells = _parse_xml_string(xml)
        assert len(spells) == 1
        assert spells[0].slug_fr == "coup-mental-i"
        lvl = spells[0].level_json
        assert lvl.get("psychiste") == 1
        assert lvl.get("mesmériste") == 1


# ── Test d'intégration : parse_dump sur XML synthétique ──────────────────────

class TestParseDump:
    def test_finds_fireball(self):
        xml = _make_xml([
            ("Pathfinder-RPG.Boule de feu", "Pathfinder-RPG.Boule de feu", FIREBALL_RAW),
            ("Pathfinder-RPG.Monstre", "Pathfinder-RPG.Monstre", NON_SPELL_RAW),
        ])
        spells = _parse_xml_string(xml)
        assert len(spells) == 1
        assert spells[0].slug_fr == "boule-de-feu"
        assert spells[0].school == "évocation"

    def test_filters_non_spells(self):
        xml = _make_xml([
            ("Pathfinder-RPG.Monstre", "Pathfinder-RPG.Monstre", NON_SPELL_RAW),
        ])
        spells = _parse_xml_string(xml)
        assert len(spells) == 0

    def test_multiple_spells(self):
        xml = _make_xml([
            ("Pathfinder-RPG.Boule de feu", "Pathfinder-RPG.Boule de feu", FIREBALL_RAW),
            ("Pathfinder-RPG.Souhait", "Pathfinder-RPG.Souhait", WISH_RAW),
            ("Pathfinder-RPG.Charme-personne", "Pathfinder-RPG.Charme-personne", CHARM_RAW),
        ])
        spells = _parse_xml_string(xml)
        assert len(spells) == 3
        slugs = {s.slug_fr for s in spells}
        assert "boule-de-feu" in slugs
        assert "souhait" in slugs
        assert "charme-personne" in slugs

    def test_description_extracted(self):
        xml = _make_xml([
            ("Pathfinder-RPG.Boule de feu", "Pathfinder-RPG.Boule de feu", FIREBALL_RAW),
        ])
        spells = _parse_xml_string(xml)
        assert "boule de feu" in spells[0].description_fr.lower()

    def test_raw_url_built(self):
        xml = _make_xml([
            ("Pathfinder-RPG.Boule de feu", "Pathfinder-RPG.Boule de feu", FIREBALL_RAW),
        ])
        spells = _parse_xml_string(xml)
        assert spells[0].raw_url is not None
        assert "pathfinder-fr.org" in spells[0].raw_url
