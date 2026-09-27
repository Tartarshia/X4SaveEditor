import gzip
import hashlib
import tempfile
from pathlib import Path
import unittest

import core


class CodecTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.xml = ('<?xml version="1.0" encoding="UTF-8"?>\r\n'
                    '<savegame><!--preserve--><info><player name="中文 &amp; &quot;名字&quot;" money=\'42\'/></info>'
                    '<universe><node id="[0xabc]" name="ship > 2" x="&lt;"/>text<![CDATA[<raw>]]>'
                    '<node><empty/></node></universe></savegame>').encode()
        self.source = self.root / 'source.xml.gz'
        self.source.write_bytes(gzip.compress(self.xml))
        self.original_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.folder, self.meta = core.build_index(self.source, self.root / 'cache')

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.original_hash)
        self.tmp.cleanup()

    def test_hierarchy_and_offsets(self):
        self.assertEqual(self.meta['nodes'], 7)
        self.assertEqual([r[1] for r in core.query(self.folder, 'children', 1)], ['info', 'universe'])
        row = core.query(self.folder, 'id', '[0xabc]')[0]
        attrs, preview = core.details(self.folder, row[0])
        self.assertEqual(attrs['name'], 'ship > 2')
        self.assertTrue(preview.startswith('<node id='))

    def test_noop_is_byte_identical(self):
        output = self.root / 'copy.xml.gz'
        core.export_save(self.folder, {}, output)
        self.assertEqual(gzip.decompress(output.read_bytes()), self.xml)

    def test_edit_preserves_other_bytes_and_entities(self):
        output = self.root / 'edited.xml.gz'
        core.export_save(self.folder, {3: {'money': '123456'}}, output)
        self.assertEqual(gzip.decompress(output.read_bytes()), self.xml.replace(b"money='42'", b"money='123456'"))

    def test_unicode_quotes_newline_roundtrip(self):
        value = '新名称 " & < > \'\r\n\t'
        output = self.root / 'edited.xml'
        core.export_save(self.folder, {3: {'name': value}}, output)
        self.assertEqual(core.validate(output, {3: {'name': value}}), 7)

    def test_no_overwrite(self):
        with self.assertRaises(ValueError):
            core.export_save(self.folder, {}, self.source)

    def test_bad_attributes_rejected(self):
        for edits in [{'absent': '1'}, {'name': '\x00'}]:
            output = self.root / 'bad.xml'
            with self.assertRaises(Exception):
                core.export_save(self.folder, {3: edits}, output)
            self.assertFalse(output.exists())

    def test_damaged_cache_not_published(self):
        snapshot = Path(self.folder) / 'source.xml'
        snapshot.write_bytes(self.xml.replace(b"money='42'", b"money='43'"))
        output = self.root / 'bad.xml'
        with self.assertRaises(ValueError):
            core.export_save(self.folder, {}, output)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob('.x4-export-*')))

    def test_cache_reuse(self):
        self.assertEqual(core.build_index(self.source, self.root / 'cache'), (self.folder, self.meta))

    def test_malformed_and_dtd_cleanup(self):
        for xml in [b'<savegame><bad></savegame>', b'<!DOCTYPE a [<!ENTITY b "bad">]><a>&b;</a>', '<a/>'.encode('utf-16')]:
            other = self.root / 'bad.xml'
            other.write_bytes(xml)
            with self.assertRaises(Exception):
                core.build_index(other, self.root / 'cache')
            self.assertEqual(len(list((self.root / 'cache').iterdir())), 1)

    def test_page_cursor_and_text_search(self):
        other = self.root / 'many.xml'
        other.write_text('<savegame>' + ''.join(f'<item id="{i}" name="ship {i}"/>' for i in range(600)) + '</savegame>')
        folder, _ = core.build_index(other, self.root / 'cache')
        rows = core.query(folder, 'tag', 'item')
        self.assertEqual(len(rows), 201)
        next_rows = core.query(folder, 'tag', 'item', rows[199][0])
        self.assertEqual(next_rows[0][0], rows[200][0])
        self.assertEqual(len(core.query(folder, 'text', 'ship 599')), 1)

    def test_multiple_patches_different_lengths(self):
        output = self.root / 'edited.xml'
        core.export_save(self.folder, {3: {'money': '0'}, 5: {'name': 'longer ship name', 'x': '>'}}, output)
        self.assertEqual(core.validate(output, {3: {'money': '0'}, 5: {'name': 'longer ship name', 'x': '>'}}), 7)


if __name__ == '__main__':
    unittest.main()
