"""Synthetic assets and local map resources; no game or user data."""
from pathlib import Path
import tempfile
import unittest
import core
from gameplay import Editor
from test_expansion import EXPANSION_SAVE,make_expansion_game

ASSET_SAVE=(EXPANSION_SAVE
    .replace('<info>','<info><patches><patch extension="ego_dlc_split"/></patches>',1)
    .replace('<hull value="50"/>','<inventory><ware ware="inv_training" amount="2"/></inventory><hull value="50"/>',1)
    .replace('name="Factory A" code="ST-A">','name="Factory A" code="ST-A"><inventory><ware ware="inv_setapart" amount="4"/></inventory><connections><connection><component class="npc" owner="player" name="Manager"><traits><skills management="3"/></traits><entity post="manager"/></component></connection></connections>',1)
    .replace('</component></universe>','</component><component class="sector" id="sector-other" macro="sector_other" owner="teladi"><offset><position x="500" z="400"/></offset></component></universe>',1))

def make_asset_game(root):
    make_expansion_game(root)
    (root/'libraries/mapdefaults.xml').write_text('<defaults><dataset macro="sector_test"><properties><identification name="Home Sector"/></properties></dataset></defaults>','utf-8')
    ext=root/'extensions/ego_dlc_split';(ext/'libraries').mkdir(parents=True)
    (ext/'content.xml').write_text('<content name="Test Split"/>','utf-8')
    (ext/'libraries/mapdefaults.xml').write_text('<defaults><dataset macro="sector_other"><properties><identification name="Other Sector"/></properties></dataset></defaults>','utf-8')
    maps=root/'maps/xu_ep2_universe';maps.mkdir(parents=True)
    (maps/'galaxy.xml').write_text('''<macros><macro name="universe"><connections>
      <connection name="home" ref="clusters"><macro ref="cluster_home"/></connection>
      <connection name="other" ref="clusters"><macro ref="cluster_other"/></connection>
      <connection name="gate" ref="destination" path="../home/sector/gate"><macro path="../../../other/sector/gate"/></connection>
      <connection name="reverse" ref="destination" path="../other/sector/gate"><macro path="../../../home/sector/gate"/></connection>
      <connection name="unknown" ref="destination" path="../absent/sector/gate"><macro path="../../../other/sector/gate"/></connection>
    </connections></macro></macros>''','utf-8')
    (maps/'clusters.xml').write_text('''<macros>
      <macro name="cluster_home"><connections><connection name="sector" ref="sectors"><macro ref="sector_test"/></connection></connections></macro>
      <macro name="cluster_other"><connections><connection name="sector" ref="sectors"><macro ref="sector_other"/></connection></connections></macro>
    </macros>''','utf-8')

class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        make_asset_game(self.root/'game');source=self.root/'save.xml';source.write_text(ASSET_SAVE,'utf-8')
        folder,_=core.build_index(source,self.root/'cache');self.e=Editor(folder,self.root/'game')
    def tearDown(self):self.e.close();self.temp.cleanup()

    def test_directory_filters_and_paginates_only_player_assets(self):
        data=self.e.view({'kind':'assets'})
        self.assertEqual(data['total'],len(self.e.assets))
        self.assertNotIn('Enemy Factory',{r['name'] for r in data['rows']})
        ships=self.e.view({'kind':'assets','assetKind':'ship'})
        self.assertTrue(all(r['kind']=='ship' for r in ships['rows']))
        station=self.e.view({'kind':'assets','search':'ST-A'})['rows'][0]
        self.assertEqual(station['name'],'Factory A')
        self.assertEqual(self.e.view({'kind':'assets','sector':'not-a-sector'})['total'],0)
        self.assertEqual(self.e.view({'kind':'assets','page':1})['rows'],[])

    def test_asset_details_scope_accounts_people_and_inventory(self):
        ship=self.e.view({'kind':'asset_detail','id':self.e.current})
        self.assertEqual(ship['kind'],'ship');self.assertIsNone(ship['account'])
        station=next(n for n in self.e.station_accounts if self.e.asset_name(n)=='Factory A')
        detail=self.e.view({'kind':'asset_detail','id':station})
        self.assertEqual(detail['account']['amount'],75)
        people=self.e.view({'kind':'crew','ship':station})
        self.assertEqual([r['name'] for r in people['rows']],['Manager'])
        self.assertEqual(len(self.e.view({'kind':'station_money','station':station})['rows']),1)
        inventory=self.e.view({'kind':'inventory','asset':station})
        self.assertEqual([r['name'] for r in inventory['locations']],['Factory A'])
        self.assertEqual(inventory['items'][0]['id'],'inv_setapart')
        with self.assertRaises(ValueError):self.e.view({'kind':'inventory','asset':station,'holder':ship['inventoryLocations'][0]['id']})
        with self.assertRaises(ValueError):self.e.view({'kind':'asset_detail','id':self.e.player})

    def test_map_resolves_connections_sources_owners_and_sector_assets(self):
        data=self.e.view({'kind':'map'});sectors={r['macro']:r for r in data['sectors']}
        self.assertEqual(len(data['connections']),1)
        self.assertEqual(set(data['connections'][0].values()),{sectors['sector_test']['id'],sectors['sector_other']['id']})
        self.assertEqual(sectors['sector_other']['source']['id'],'ego_dlc_split')
        self.assertEqual(sectors['sector_test']['ownerName'],'Argon')
        home=self.e.view({'kind':'map','sector':sectors['sector_test']['id']})
        self.assertEqual(home['assets']['total'],len(self.e.assets))
        other=self.e.view({'kind':'map','sector':sectors['sector_other']['id']})
        self.assertEqual(other['assets']['total'],0)

    def test_map_intra_cluster_accelerators_use_sector_references(self):
        maps=self.root/'game/maps/xu_ep2_universe'
        (maps/'clusters.xml').write_text('''<macros><macro name="cluster_home"><connections>
        <connection name="a" ref="sectors"><macro ref="sector_test"/></connection>
        <connection name="b" ref="sectors"><macro ref="sector_other"/></connection>
        <connection name="accelerator" ref="destination" path="../a/zone/gate"><macro path="../../../b/zone/gate"/></connection>
        </connections></macro></macros>''','utf-8')
        self.e.close();self.e=Editor(self.e.folder,self.root/'game')
        self.assertIn({'from':'sector_test','to':'sector_other','name':'accelerator'},self.e.game.map_connections())

    def test_player_stations_are_known_when_save_omits_discovery_flags(self):
        before=(self.e.folder/'source.xml').read_bytes()
        data=self.e.view({'kind':'map'});rows={r['name']:r for r in data['objects']['rows']}
        self.assertTrue(rows['Factory A']['known']);self.assertEqual(rows['Factory A']['knowledge'],'owned')
        self.assertTrue(rows['Factory B']['known'])
        self.assertFalse(rows['Enemy Factory']['known'])
        self.assertEqual(before,(self.e.folder/'source.xml').read_bytes())
        for attrs,known,reason in [({'owner':'player','known':'0'},True,'owned'),
                                   ({'knownto':'argon player'},True,'saved'),
                                   ({'knownto':'argon'},False,'unknown'),
                                   ({'known':'1'},True,'saved'),({},False,'unknown')]:
            self.assertEqual(self.e.map_knowledge(attrs),{'known':known,'knowledge':reason})
