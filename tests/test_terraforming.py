"""Synthetic terraforming records; never includes extracted game resources."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import core
from gameplay import Editor
from test_expansion import EXPANSION_SAVE, make_expansion_game

TERRAFORMING='''<terraforming part="planet" active="" missioncue="123"><stats>
<stat id="temperature" value="6"/><stat id="population" value="250000000"/>
<stat id="unknown" value="1"/></stats><projects>
<project id="water" name="Water project" group="water" duration="600" starttime="-1" repeatcooldown="0">
<scaledresources><ware ware="ore" amount="2"/></scaledresources></project>
<project id="housing" name="Housing" group="housing" completed="1" repeatcooldown="-1">
<scaledresources><ware ware="ore" amount="3"/></scaledresources></project>
</projects><shadervalues><shadervalue name="waterlevel" endvalue="0.1"/></shadervalues></terraforming>'''
TERRA_SAVE=(EXPANSION_SAVE.replace('<universe>','<universe><component class="cluster" macro="cluster_test" id="cluster">'+TERRAFORMING)
            .replace('</universe>','</component></universe>'))

def make_terraforming_game(root):
    make_expansion_game(root)
    (root/'libraries/terraforming.xml').write_text('''<terraforming><stats>
<stat id="temperature" name="Temperature"><range end="3" description="Cold"/>
<range end="5" description="Temperate"/><range end="9" description="Hot"/></stat>
<stat id="population" name="Population"/></stats><projectgroups>
<projectgroup id="water" name="Water"/><projectgroup id="housing" name="Housing"/>
</projectgroups></terraforming>''','utf-8')

class TerraformingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        make_terraforming_game(self.root/'game');self.e=self.open(TERRA_SAVE)

    def open(self,xml):
        source=self.root/f'save-{len(list(self.root.glob("save-*")))}.xml';source.write_text(xml,'utf-8')
        folder,_=core.build_index(source,self.root/'cache');return Editor(folder,self.root/'game')

    def tearDown(self):self.e.close();self.temp.cleanup()

    def test_catalogue_status_and_actual_resources(self):
        data=self.e.terraforming_data({});self.assertTrue(data['hqHere'])
        self.assertEqual(data['total'],2);self.assertEqual(data['stats'][0]['status'],'Hot')
        self.assertTrue(data['stats'][0]['editable']);self.assertFalse(data['stats'][1]['editable'])
        self.assertFalse(data['stats'][2]['editable']);self.assertFalse(data['planet']['missionCompleted'])
        water=next(r for r in data['rows'] if r['key']=='water')
        self.assertTrue(water['canSupply']);self.assertEqual(water['resources'][0]['amount'],2)
        self.assertFalse(next(r for r in data['rows'] if r['key']=='housing')['canSupply'])

    def test_combined_export_preserves_state_and_source(self):
        d=self.e.terraforming_data({});water=next(r for r in d['rows'] if r['key']=='water')
        cmds=[{'kind':'terraforming_stat','id':d['stats'][0]['id'],'planet':d['planet']['id'],'value':5},
              {'kind':'terraforming_stock','id':water['id'],'planet':d['planet']['id'],'value':1}]
        before=(self.e.folder/'source.xml').read_bytes();plan=self.e.plan(cmds)
        out=self.root/'export.xml.gz';plan.export({},out,lambda m:None)
        with gzip.open(out,'rb') as f:raw=f.read()
        tree=ET.fromstring(raw)
        self.assertEqual(tree.find('.//terraforming/stats/stat').get('value'),'5')
        self.assertEqual(tree.find('.//component[@macro="station_pla_headquarters_base_01_macro"]//cargo/ware').get('amount'),'2')
        self.assertIn(b'missioncue="123"',raw);self.assertIn(b'endvalue="0.1"',raw)
        self.assertEqual(ET.tostring(tree.find('.//terraforming/projects')),ET.tostring(ET.fromstring(TERRA_SAVE).find('.//terraforming/projects')))
        self.assertEqual(before,(self.e.folder/'source.xml').read_bytes())
        self.assertEqual(len(self.e.source_nodes(cmds[1])['nodes']),2)

    def test_stat_range_and_identity_guards(self):
        d=self.e.terraforming_data({});p=d['planet']['id'];n=d['stats'][0]['id']
        for value in (-1,10,'nan','inf',True):
            with self.assertRaises(ValueError):self.e.plan([{'kind':'terraforming_stat','id':n,'planet':p,'value':value}])
        for row in d['stats'][1:]:
            with self.assertRaises(ValueError):self.e.plan([{'kind':'terraforming_stat','id':row['id'],'planet':p,'value':0}])
        with self.assertRaises(ValueError):self.e.terraforming_data({'planet':n})
        with self.assertRaises(ValueError):self.e.source_nodes({'kind':'terraforming_project','id':n,'planet':p})

    def test_active_and_duplicate_stats_are_read_only(self):
        for xml in (TERRA_SAVE.replace('active=""','active="water"'),
                    TERRA_SAVE.replace('<stat id="temperature" value="6"/>','<stat id="temperature" value="6"/><stat id="temperature" value="5"/>')):
            e=self.open(xml)
            try:
                d=e.terraforming_data({});self.assertFalse(d['stats'][0]['editable'])
                with self.assertRaises(ValueError):e.plan([{'kind':'terraforming_stat','id':d['stats'][0]['id'],'planet':d['planet']['id'],'value':5}])
            finally:e.close()

    def test_supply_capacity_location_active_and_conflicts(self):
        variants=[TERRA_SAVE.replace('amount="2"/></scaledresources>','amount="100000"/></scaledresources>'),
                  TERRA_SAVE.replace('active=""','active="water"'),
                  TERRA_SAVE.replace('station_pla_headquarters_base_01_macro','ordinary_station'),
                  TERRA_SAVE.replace('<ware ware="ore" amount="2"/></scaledresources>','<ware ware="ore" amount="2"/><ware ware="ore" amount="2"/></scaledresources>')]
        for xml in variants:
            e=self.open(xml)
            try:
                d=e.terraforming_data({});r=next(r for r in d['rows'] if r['key']=='water')
                with self.assertRaises(ValueError):e.plan([{'kind':'terraforming_stock','id':r['id'],'planet':d['planet']['id'],'value':1}])
            finally:e.close()
        d=self.e.terraforming_data({});r=next(r for r in d['rows'] if r['key']=='water')
        hq=self.e.headquarters()[0]
        with self.assertRaises(ValueError):self.e.plan([
            {'kind':'station_stock','id':hq,'storage':'ore','value':0},
            {'kind':'terraforming_stock','id':r['id'],'planet':d['planet']['id'],'value':1}])

    def test_multiple_supply_actions_merge_without_double_counting(self):
        xml=TERRA_SAVE.replace('</projects>','<project id="second" name="Second"><scaledresources><ware ware="ore" amount="3"/></scaledresources></project></projects>')
        e=self.open(xml)
        try:
            d=e.terraforming_data({})
            commands=[{'kind':'terraforming_stock','id':r['id'],'planet':d['planet']['id'],'value':1}
                      for r in d['rows'] if r['key'] in ('water','second')]
            plan=e.plan(commands)
            self.assertTrue(any('3' in fragment for fragments in plan.children.values() for fragment in fragments))
        finally:e.close()

    def test_search_pagination_and_empty_records(self):
        projects=''.join(f'<project id="p{i}" name="Extra {i}"/>' for i in range(61))
        e=self.open(TERRA_SAVE.replace('</projects>',projects+'</projects>'))
        try:
            self.assertEqual(e.terraforming_data({})['total'],63)
            self.assertEqual(len(e.terraforming_data({'page':1})['rows']),13)
            self.assertEqual(e.terraforming_data({'search':'water'})['total'],1)
        finally:e.close()

    def test_unrecognised_values_stay_read_only_and_json_safe(self):
        e=self.open(TERRA_SAVE.replace('value="6"','value="nan"').replace('completed="1"','completed="unknown"'))
        try:
            d=e.terraforming_data({});json.dumps(d,allow_nan=False)
            self.assertIsNone(d['stats'][0]['value']);self.assertFalse(d['stats'][0]['editable'])
            housing=next(r for r in d['rows'] if r['key']=='housing')
            self.assertIsNone(housing['completed']);self.assertFalse(housing['canSupply'])
        finally:e.close()
        e=self.open(EXPANSION_SAVE)
        try:self.assertEqual(e.terraforming_data({})['planets'],[])
        finally:e.close()
