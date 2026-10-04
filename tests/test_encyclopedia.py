"""Encyclopedia provenance from wholly synthetic base/DLC resource layers."""
from pathlib import Path
import tempfile
import unittest
import core
from gameplay import Editor
from test_assets import ASSET_SAVE,make_asset_game

ENCYCLOPEDIA_SAVE=ASSET_SAVE.replace('<entry id="ore"/>','<entry id="ore"/><entry id="unknown_item"/>',1)

def make_encyclopedia_game(root):
    make_asset_game(root)
    ext=root/'extensions/ego_dlc_split'
    additions=''.join(f'<ware id="dlc_item_{i}" name="Expansion Item {i:03}" transport="inventory" tags="inventory"/>' for i in range(121))
    (ext/'libraries/wares.xml').write_text('''<diff>
      <replace sel="/wares/ware[@id='inv_training']"><ware id="inv_training" name="Updated Training" transport="inventory" tags="inventory seminar"/></replace>
      <add sel="/wares">'''+additions+'''<ware id="dlc_engine" name="Expansion Engine" transport="equipment" group="engines"><component ref="dlc_engine_macro"/></ware></add>
    </diff>''','utf-8')
    macros=ext/'assets/test/macros';macros.mkdir(parents=True)
    (macros/'dlc_engine_macro.xml').write_text('<macros><macro name="dlc_engine_macro" class="engine"><component ref="dlc_engine"/><properties><identification name="Expansion Engine" type="enginetypes"/></properties></macro></macros>','utf-8')
    # A property-only DLC patch of an existing base macro must retain base origin.
    (macros/'engine_test_macro.xml').write_text('''<diff><replace sel="/macros/macro/properties/identification/@name">Updated Engine</replace></diff>''','utf-8')

class EncyclopediaSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        make_encyclopedia_game(self.root/'game');source=self.root/'save.xml';source.write_text(ENCYCLOPEDIA_SAVE,'utf-8')
        folder,_=core.build_index(source,self.root/'cache');self.e=Editor(folder,self.root/'game')
    def tearDown(self):self.e.close();self.temp.cleanup()

    def test_original_definitions_survive_later_ware_and_macro_updates(self):
        game=self.e.game
        self.assertEqual(game.wares['inv_training']['name'],'Updated Training')
        self.assertEqual(game.encyclopedia_source('inv_training')['id'],'base')
        self.assertEqual(game.model_name('engine_test_macro'),'Updated Engine')
        self.assertEqual(game.encyclopedia_source('engine_test_macro')['id'],'base')
        self.assertEqual(game.encyclopedia_source('dlc_engine_macro'),{'id':'ego_dlc_split','name':'Test Split'})
        self.assertEqual(game.encyclopedia_source('dlc_item_0')['id'],'ego_dlc_split')

    def test_source_filter_combines_status_category_search_and_pagination(self):
        request={'kind':'encyclopedia','source':'ego_dlc_split','status':'unknown','group':'inventory_wares','search':'Expansion Item'}
        first=self.e.view(request);second=self.e.view({**request,'page':1})
        self.assertEqual(first['total'],121);self.assertEqual(len(first['rows']),100);self.assertEqual(len(second['rows']),21)
        self.assertTrue(all(r['source']['id']=='ego_dlc_split' and not r['known'] for r in first['rows']+second['rows']))
        self.assertEqual(first['sources'],self.e.view({**request,'source':'base'})['sources'])
        known=self.e.view({'kind':'encyclopedia','status':'known','source':'unknown'})
        self.assertEqual([r['identity'] for r in known['rows']],['unknown_item'])
        self.assertEqual(known['rows'][0]['source']['name'],'来源未确认')

    def test_dlc_label_does_not_change_unlock_commands_or_export(self):
        row=self.e.view({'kind':'encyclopedia','source':'ego_dlc_split','search':'dlc_item_0','status':'unknown'})['rows'][0]
        before=(self.e.folder/'source.xml').read_bytes()
        target=self.root/'out.xml'
        self.e.plan([{'kind':'encyclopedia','id':row['identity'],'storage':row['group'],'value':1}]).export({},target,lambda m:None)
        self.assertEqual(before,(self.e.folder/'source.xml').read_bytes())
        text=target.read_text('utf-8');self.assertIn('id="dlc_item_0"',text)
        self.assertNotIn('source="ego_dlc_split"',text)
