"""Tests unitaires du parser pathfinder-fr."""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET

import pytest

from src.ingest.parser_fr import (
    _clean_wiki,
    _is_spell,
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
        school, subschool, descriptors = _parse_school(FIREBALL_RAW)
        assert school == "évocation"
        assert "feu" in descriptors

    def test_universal(self):
        school, subschool, descriptors = _parse_school(WISH_RAW)
        assert school == "universel"

    def test_enchantement_with_subschool(self):
        school, subschool, descriptors = _parse_school(CHARM_RAW)
        assert school == "enchantement"
        assert "mental" in descriptors

    def test_no_school_returns_empty(self):
        school, _, _ = _parse_school(NON_SPELL_RAW)
        assert school == ""


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
