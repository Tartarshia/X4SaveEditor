from pathlib import Path
import tempfile
import unittest

import core
import shortcuts


XML = '''<savegame><info><player money="42"/></info><universe><factions>
<faction id="player"><relations><relation faction="argon" relation="0.1"/></relations>
<licences><licence type="trade" factions="argon"/></licences><account id="shared" amount="42"/></faction>
<faction id="argon"><relations><relation faction="player" relation="0.2"/><booster faction="player" relation="0.01"/>
<relation faction="teladi" relation="0.3"/></relations></faction></factions>
<component class="player" owner="player" id="actor"><inventory><ware ware="personal" amount="5"/></inventory>
<blueprints><blueprint ware="ship_a"/></blueprints><research><research ware="tech_a" research="1"/></research><known/></component>
<component class="npc" owner="argon"><inventory><ware ware="npc_item" amount="5"/></inventory><traits><skills piloting="2"/></traits></component>
<component class="ship_m" owner="player" id="ship"><account id="shared" amount="42"/><ammunition/><modification/>
<people><person><traits><skills piloting="8"/></traits></person></people>
<component class="storage"><cargo><ware ware="cargo_item" amount="3"/></cargo></component>
<component class="npc" owner="argon"><traits><skills piloting="4"/></traits></component></component>
<component class="station" owner="player" id="station"><account id="station_account" amount="42"/></component>
<component class="buildstorage" owner="player"/>
<component class="ship_l" owner="player_ally" id="ally"><ammunition/><modification/></component>
</universe><stats><stat id="money_player" value="42"/></stats><missions><mission id="mission_a"/></missions></savegame>'''


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.source = root/'save.xml'
        self.source.write_text(XML,'utf-8')
        self.folder, _ = core.build_index(self.source,root/'cache')
        self.catalog = {row['key']: row for row in shortcuts.catalog(self.folder)}

    def tearDown(self):
        self.assertEqual(self.source.read_text('utf-8'),XML)
        self.assertEqual((Path(self.folder)/'source.xml').read_text('utf-8'),XML)
        self.tmp.cleanup()

    def rows(self,key):
        return shortcuts.query(self.folder,key)

    def attrs(self,key):
        return [core.details(self.folder,r[0])[0] for r in self.rows(key)]

    def test_money_follows_identity_not_equal_amount(self):
        self.assertEqual(self.catalog['money']['count'],4)
        ids = [row[4] for row in self.rows('money')]
        self.assertEqual(ids.count('shared'),2)
        self.assertNotIn('station_account',ids)

    def test_player_containers_exclude_npc_inventory(self):
        self.assertEqual(self.attrs('inventory'),[{'ware':'personal','amount':'5'}])
        self.assertEqual(self.attrs('blueprints'),[{'ware':'ship_a'}])
        self.assertEqual(self.attrs('research'),[{'ware':'tech_a','research':'1'}])

    def test_exact_ownership_and_inherited_storage(self):
        self.assertEqual([row[4] for row in self.rows('ships')],['ship'])
        self.assertEqual([row[4] for row in self.rows('stations')],['station'])
        self.assertEqual(self.catalog['cargo']['count'],2)
        self.assertEqual(self.catalog['modifications']['count'],1)
        self.assertEqual(self.attrs('skills'),[{'piloting':'8'}])

    def test_bidirectional_relations_and_temporary_booster(self):
        rows=self.rows('reputation')
        self.assertEqual(len(rows),3)
        self.assertTrue(any('argon → player' in r[5] for r in rows))
        self.assertTrue(any('player → argon' in r[5] for r in rows))
        self.assertTrue(any('临时 booster' in r[5] for r in rows))

    def test_missing_nodes_and_cache_reuse(self):
        path=shortcuts.ensure_index(self.folder)
        timestamp=path.stat().st_mtime_ns
        shortcuts.catalog(self.folder)
        self.assertEqual(path.stat().st_mtime_ns,timestamp)
        other=self.source.parent/'empty.xml'
        other.write_text('<savegame/>')
        folder,_=core.build_index(other,self.source.parent/'othercache')
        self.assertTrue(all(r['count']==0 for r in shortcuts.catalog(folder)))
        self.assertEqual(shortcuts.query(folder,'money'),[])
        with self.assertRaises(ValueError):
            shortcuts.query(folder,'arbitrary_sql')

    def test_shortcut_pagination(self):
        other=self.source.parent/'many.xml'
        other.write_text('<savegame>' + ''.join(f'<component class="ship_s" owner="player" id="ship{i}"/>' for i in range(450)) + '</savegame>')
        folder,_=core.build_index(other,self.source.parent/'othercache')
        first=shortcuts.query(folder,'ships')
        self.assertEqual(len(first),201)
        second=shortcuts.query(folder,'ships',first[199][0])
        self.assertEqual(second[0][0],first[200][0])


if __name__ == '__main__':
    unittest.main()
