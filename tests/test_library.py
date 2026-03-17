"""Tests for xschem library resolution."""

import shutil
from pathlib import Path

from pyxschem import SymbolLibrary, XschemConfig
from pyxschem.library import _parse_xschemrc

SYM_FIXTURES = Path(__file__).parent / "fixtures" / "real" / "sym"


def _make_lib(tmp_path, structure: dict[str, list[str]]) -> list[Path]:
    """Create mock library structure. Returns list of lib paths.

    structure: {"devices": ["res.sym", "cap.sym"], "pdk": ["nmos.sym"]}
    Copies real .sym fixtures where available, creates empty files otherwise.
    """
    paths = []
    for lib_name, sym_files in structure.items():
        lib_dir = tmp_path / lib_name
        for sym_file in sym_files:
            sym_dir = lib_dir / Path(sym_file).parent
            sym_dir.mkdir(parents=True, exist_ok=True)
            # Copy from real fixtures if available
            real = SYM_FIXTURES / Path(sym_file).name
            dest = lib_dir / sym_file
            if real.exists():
                shutil.copy(real, dest)
            else:
                dest.write_text(
                    "v {xschem version=3.4.5 file_version=1.2}\n"
                    "G {}\nK {}\nV {}\nS {}\nE {}\n"
                )
        paths.append(lib_dir)
    return paths


class TestXschemConfigParsing:
    def test_set_and_append(self):
        text = (
            'set XSCHEM_LIBRARY_PATH {}\n'
            'append XSCHEM_LIBRARY_PATH :/usr/share/xschem/devices\n'
            'append XSCHEM_LIBRARY_PATH :/home/user/mylib\n'
        )
        paths = _parse_xschemrc(text)
        assert len(paths) == 2
        assert paths[0] == Path("/usr/share/xschem/devices")
        assert paths[1] == Path("/home/user/mylib")

    def test_variable_substitution(self):
        text = (
            'set MYDIR /opt/pdk\n'
            'set XSCHEM_LIBRARY_PATH {}\n'
            'append XSCHEM_LIBRARY_PATH :$MYDIR/symbols\n'
        )
        paths = _parse_xschemrc(text)
        assert paths[0] == Path("/opt/pdk/symbols")

    def test_braced_variable_substitution(self):
        text = (
            'set MYDIR /opt/pdk\n'
            'set XSCHEM_LIBRARY_PATH {}\n'
            'append XSCHEM_LIBRARY_PATH :${MYDIR}/symbols\n'
        )
        paths = _parse_xschemrc(text)
        assert paths[0] == Path("/opt/pdk/symbols")

    def test_env_substitution(self, monkeypatch):
        monkeypatch.setenv("MY_TEST_PDK", "/custom/pdk")
        text = (
            'set XSCHEM_LIBRARY_PATH {}\n'
            'append XSCHEM_LIBRARY_PATH :$env(MY_TEST_PDK)/xschem\n'
        )
        paths = _parse_xschemrc(text)
        assert paths[0] == Path("/custom/pdk/xschem")

    def test_comments_skipped(self):
        text = (
            '# This is a comment\n'
            'set XSCHEM_LIBRARY_PATH {}\n'
            '# append XSCHEM_LIBRARY_PATH :/skip/this\n'
            'append XSCHEM_LIBRARY_PATH :/keep/this\n'
        )
        paths = _parse_xschemrc(text)
        assert len(paths) == 1
        assert paths[0] == Path("/keep/this")

    def test_blank_lines_skipped(self):
        text = (
            '\n'
            'set XSCHEM_LIBRARY_PATH {}\n'
            '\n'
            'append XSCHEM_LIBRARY_PATH :/some/path\n'
            '\n'
        )
        paths = _parse_xschemrc(text)
        assert len(paths) == 1

    def test_empty_path_returns_empty(self):
        text = '# nothing here\n'
        paths = _parse_xschemrc(text)
        assert paths == []

    def test_load_from_file(self, tmp_path):
        rc = tmp_path / "xschemrc"
        rc.write_text(
            'set XSCHEM_LIBRARY_PATH {}\n'
            'append XSCHEM_LIBRARY_PATH :/usr/share/xschem/devices\n'
        )
        config = XschemConfig.load(rc)
        assert len(config.library_paths) == 1

    def test_from_paths(self, tmp_path):
        config = XschemConfig.from_paths([tmp_path / "a", tmp_path / "b"])
        assert len(config.library_paths) == 2


class TestSymbolLibraryResolve:
    def test_resolve_finds_symbol(self, tmp_path):
        paths = _make_lib(tmp_path, {"lib": ["devices/res.sym"]})
        lib = SymbolLibrary(paths)
        sym = lib.resolve("devices/res.sym")
        assert sym is not None
        assert sym.type == "resistor"

    def test_resolve_returns_none_for_missing(self, tmp_path):
        paths = _make_lib(tmp_path, {"lib": ["devices/res.sym"]})
        lib = SymbolLibrary(paths)
        assert lib.resolve("nonexistent.sym") is None

    def test_resolve_first_path_wins(self, tmp_path):
        # Create two libs with same symbol name
        lib1 = tmp_path / "lib1"
        lib2 = tmp_path / "lib2"
        (lib1 / "devices").mkdir(parents=True)
        (lib2 / "devices").mkdir(parents=True)
        shutil.copy(SYM_FIXTURES / "res.sym", lib1 / "devices" / "res.sym")
        shutil.copy(SYM_FIXTURES / "vsource.sym", lib2 / "devices" / "res.sym")  # different file
        lib = SymbolLibrary([lib1, lib2])
        sym = lib.resolve("devices/res.sym")
        assert sym.type == "resistor"  # from lib1, not lib2

    def test_resolve_with_pins(self, tmp_path):
        paths = _make_lib(tmp_path, {"lib": ["devices/nmos4.sym"]})
        lib = SymbolLibrary(paths)
        sym = lib.resolve("devices/nmos4.sym")
        assert len(sym.pins) == 4

    def test_from_config(self, tmp_path):
        paths = _make_lib(tmp_path, {"lib": ["devices/res.sym"]})
        config = XschemConfig.from_paths(paths)
        lib = SymbolLibrary.from_config(config)
        assert lib.resolve("devices/res.sym") is not None


class TestSymbolLibraryCaching:
    def test_resolve_caches(self, tmp_path):
        paths = _make_lib(tmp_path, {"lib": ["devices/res.sym"]})
        lib = SymbolLibrary(paths)
        sym1 = lib.resolve("devices/res.sym")
        sym2 = lib.resolve("devices/res.sym")
        assert sym1 is sym2  # same object


class TestSymbolLibrarySearch:
    def test_search_finds_match(self, tmp_path):
        paths = _make_lib(tmp_path, {
            "lib": ["devices/res.sym", "devices/nmos4.sym", "devices/vsource.sym"]
        })
        lib = SymbolLibrary(paths)
        results = lib.search("res")
        assert "devices/res.sym" in results

    def test_search_case_insensitive(self, tmp_path):
        paths = _make_lib(tmp_path, {"lib": ["devices/res.sym"]})
        lib = SymbolLibrary(paths)
        assert len(lib.search("RES")) > 0
        assert len(lib.search("Res")) > 0

    def test_search_no_match(self, tmp_path):
        paths = _make_lib(tmp_path, {"lib": ["devices/res.sym"]})
        lib = SymbolLibrary(paths)
        assert lib.search("nonexistent") == []

    def test_list_symbols(self, tmp_path):
        paths = _make_lib(tmp_path, {
            "lib": ["devices/res.sym", "devices/nmos4.sym"]
        })
        lib = SymbolLibrary(paths)
        syms = lib.list_symbols()
        assert len(syms) == 2
        assert "devices/res.sym" in syms
        assert "devices/nmos4.sym" in syms
