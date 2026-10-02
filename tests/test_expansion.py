import gzip
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import core
from gameplay import Editor
from test_management import MANAGEMENT_SAVE,make_management_game

EXPANSION_SAVE=(MANAGEMENT_SAVE
    .replace('<component class="player"','<component class="sector" id="sector-test" macro="sector_test" owner="argon"><offset><position x="10" z="20"/></offset><component class="player"',1)
    .replace('</universe>','</component></universe>')
    .replace('<blueprints>','<known><entries type="wares"><entry id="ore"/></entries></known><discovered><sector id="sector-test"><boundary size="20000"/><quadtree depth="1" x="0" y="0"><node/><node state="1"/><node/><node/></quadtree></sector></discovered><blueprints>',1)
    .replace('id="ship" owner="player" name="Test ship">','id="ship" owner="player" name="Test ship" macro="test_ship"><hull value="50"/><ammunition><available><item macro="missile_test_macro" amount="2"/></available><launched><item macro="missile_test_macro" amount="1"/></launched></ammunition>')
    .replace('<person role=','<person macro="crew_test" role=')
    .replace('<connection><component class="storage" macro="test_storage">','<connection><component class="engine" macro="engine_test_macro" connection="ship"/><component class="storage" macro="test_storage">',1)
    .replace('<trade><reservations>','<traderules><wares><ware ware="ore" buy="4" sell="-1"/></wares></traderules><trade><prices><ware ware="ore" buy="10" sell="10"/><reference><ware ware="ore" buy="9" sell="9"/></reference></prices><restrictions factions="player"/><reservations>',1)
    .replace('<ware ware="ore" amount="3"/>','<ware ware="ore" amount="3" max="5"/>')
    .replace('<account id="hq-cash"/>','<account id="hq-cash"/><production ware="research_aux" endtime="110"/><connections><connection><component class="storage" macro="test_storage"><cargo/></component></connection></connections>')
    .replace('<universe>','<traderules><traderule id="4" owner="player" name="Own" factions="player" allow="1"/><traderule id="5" owner="player" name="Public" factions="argon teladi" allow="1"/></traderules><universe>'))

def make_expansion_game(root):
    make_management_game(root)
    path=root/'libraries/wares.xml'
    path.write_text(path.read_text('utf-8').replace('</wares>','''
<ware id="missile_test" name="Test Missile" group="missiles" transport="equipment" tags="equipment"><component ref="missile_test"/></ware>
<ware id="deploy_test" name="Test Satellite" group="deployables" transport="equipment" tags="equipment"><component ref="deploy_test"/></ware>
<ware id="bad_building" name="Building" group="deployables" transport="equipment" tags="module"><component ref="deploy_test"/></ware>
<ware id="engine_test" name="Engine A" group="engines" transport="equipment"><component ref="engine_test"/></ware>
<ware id="engine_alt" name="Engine B" group="engines" transport="equipment"><component ref="engine_alt"/></ware>
<ware id="engine_big" name="Big Engine" group="engines" transport="equipment"><component ref="engine_big"/></ware>
</wares>''').replace('<ware id="ore"','<ware id="ore"').replace('<research time="20">','<research time="20"><primary><ware ware="ore" amount="2"/></primary>'),'utf-8')
    # Add a verified range to the synthetic ordinary ware.
    tree=ET.parse(path);ore=tree.find('.//ware[@id="ore"]');ET.SubElement(ore,'price',min='1',average='10',max='20');tree.write(path,encoding='utf-8')
    models=root/'assets/test/macros';models.mkdir(exist_ok=True,parents=True)
    models.joinpath('test_ship.xml').write_text('<macros><macro name="test_ship" class="ship_s"><component ref="test_ship"/><properties><hull max="100"/><people capacity="8"/><storage missile="5" countermeasure="3" deployable="5" unit="2"/></properties></macro></macros>','utf-8')
    models.joinpath('missile_test_macro.xml').write_text('<macros><macro name="missile_test_macro" class="missile"><component ref="missile_test"/><properties><identification name="Test Missile" type="missiletypes"/></properties></macro></macros>','utf-8')
    models.joinpath('deploy_test_macro.xml').write_text('<macros><macro name="deploy_test_macro" class="satellite"><component ref="deploy_test"/><properties><identification name="Test Satellite" type="satellites"/></properties></macro></macros>','utf-8')
    for name,size in [('engine_test','medium'),('engine_alt','medium'),('engine_big','large')]:
        models.joinpath(name+'_macro.xml').write_text(f'<macros><macro name="{name}_macro" class="engine"><component ref="{name}"/><properties><hull max="20"/><identification name="{name}" type="enginetypes"/></properties></macro></macros>','utf-8')
        root.joinpath('assets/test',name+'.xml').write_text(f'<components><component name="{name}" class="engine"><connections><connection name="ship" tags="component engine {size}"/></connections></component></components>','utf-8')


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        make_expansion_game(self.root/'game');source=self.root/'save.xml';source.write_text(EXPANSION_SAVE,'utf-8')
        folder,_=core.build_index(source,self.root/'cache');self.e=Editor(folder,self.root/'game')

    def tearDown(self):self.e.close();self.temp.cleanup()

    def export(self,commands):
        before=(self.e.folder/'source.xml').read_bytes();target=self.root/f'out-{len(list(self.root.glob("out-*")))}.xml.gz'
        self.e.plan(commands).export({},target,lambda m:None)
        self.assertEqual(before,(self.e.folder/'source.xml').read_bytes())
        raw=gzip.decompress(target.read_bytes()).decode('utf-8');self.assertIn("<unchanged quoted='yes'><!-- keep bytes --></unchanged>",raw)
        return ET.fromstring(raw)

    def test_blueprint_revoke_preserves_other_records(self):
        tree=self.export([{'kind':'blueprint_remove','id':'old_engine'}])
        self.assertIsNone(tree.find('.//blueprint[@ware="old_engine"]'))
        self.assertEqual(self.e.source_nodes({'kind':'blueprint_remove','id':'old_engine'})['nodes'][0]['id'],self.e.children(self.e.first(self.e.player,'blueprints'),'blueprint')[0])

    def test_mod_config_adds_selected_bonus_and_removes_old_attribute(self):
        mod=next(m for m in self.e.installed_mods().values() if m['category']=='ship')
        command={'kind':'mod_config','id':mod['id'],'ware':mod['ware'],'fields':{'mass':0.75,'unitcapacity':4}}
        tree=self.export([command]);ship=tree.find('.//component[@id="ship"]/modification/ship')
        self.assertEqual(ship.attrib,{'ware':'mod_ship_test','mass':'0.75','unitcapacity':'4'})
        for fields in ({'drag':0.8},{'mass':0.75,'mystery':3},{'mass':0.1},{'mass':0.75,'unitcapacity':1.5}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):self.e.plan([{**command,'fields':fields}])
        with self.assertRaises(ValueError):self.e.plan([command,{'kind':'mod_value','id':mod['id'],'storage':'mass','value':0.8}])

    def test_ammunition_counts_reserved_and_excludes_buildings(self):
        data=self.e.ammo_data({'ship':self.e.current});self.assertEqual(data['reserved']['missile'],1)
        self.assertNotIn('bad_building',{r['ware'] for r in data['catalogue']})
        base={'kind':'ammunition','ship':self.e.current,'id':'missile_test_macro','value':4}
        tree=self.export([base,{'kind':'ammunition','ship':self.e.current,'id':'deploy_test_macro','value':3}])
        self.assertEqual(tree.find('.//component[@id="ship"]/ammunition/available/item[@macro="missile_test_macro"]').get('amount'),'4')
        self.assertEqual(tree.find('.//component[@id="ship"]/ammunition/launched/item').get('amount'),'1')
        with self.assertRaises(ValueError):self.e.plan([{**base,'value':5}])
        tree=self.export([{**base,'value':0}]);self.assertIsNone(tree.find('.//component[@id="ship"]/ammunition/available/item[@macro="missile_test_macro"]'))

    def test_repair_and_refit_preserve_ids_and_validate_connections(self):
        rows=self.e.ship_service_data({'ship':self.e.current})['rows'];engine=next(r for r in rows if r['class']=='engine')
        refit={'kind':'refit','id':engine['id'],'ship':self.e.current,'value':'engine_alt_macro'}
        tree=self.export([refit,{'kind':'repair','id':self.e.current,'ship':self.e.current,'value':100}])
        self.assertEqual(tree.find('.//component[@id="ship"]/hull').get('value'),'100')
        self.assertIsNotNone(tree.find('.//component[@class="engine"][@macro="engine_alt_macro"]'))
        with self.assertRaises(ValueError):self.e.plan([{**refit,'value':'engine_big_macro'}])
        self.export([{**refit,'value':'engine_big_macro','experimental':True}])
        with self.assertRaises(ValueError):self.e.plan([refit,{'kind':'repair','id':engine['id'],'ship':self.e.current,'value':100}])

    def test_repair_uses_final_pending_hull_modification(self):
        mod=next(m for m in self.e.installed_mods().values() if m['category']=='ship')
        spec=self.e.game.modifications[('ship',mod['ware'])]
        spec['fields']['maxhull']={'min':1.,'max':1.5}
        tree=self.export([{'kind':'mod_config','id':mod['id'],'ware':mod['ware'],'fields':{'mass':0.75,'maxhull':1.5}},
                          {'kind':'repair','id':self.e.current,'ship':self.e.current,'value':100}])
        self.assertEqual(tree.find('.//component[@id="ship"]/hull').get('value'),'150')

    def test_roster_add_remove_and_roles_preserve_named_officers(self):
        roster=self.e.crew_roster({'ship':self.e.current});self.assertEqual(roster['capacity'],8)
        count={'kind':'crew_count','id':self.e.current,'storage':'service','value':3}
        tree=self.export([count]);people=tree.find('.//component[@id="ship"]/people')
        self.assertEqual(len(people.findall('person[@role="service"]')),3)
        self.assertIsNotNone(tree.find('.//component[@name="Captain"]'))
        tree=self.export([{**count,'value':0}]);self.assertEqual(len(tree.findall('.//component[@id="ship"]/people/person')),1)
        role={'kind':'crew_role','id':roster['rows'][0]['id'],'value':'marine'}
        tree=self.export([role]);self.assertEqual(len(tree.findall('.//component[@id="ship"]/people/person[@role="marine"]')),2)
        with self.assertRaises(ValueError):self.e.plan([{**count,'value':8}])

    def test_map_reveal_preserves_other_knowledge_and_unlocks_encyclopedia(self):
        data=self.e.map_data({});self.assertEqual(len(data['sectors']),1)
        sector=data['selected'];tree=self.export([{'kind':'map_known','id':sector,'value':1},{'kind':'map_reveal','id':sector,'value':1}])
        self.assertEqual(tree.find('.//component[@class="sector"]').get('known'),'1')
        self.assertEqual({n.get('state') for n in tree.findall('.//discovered/sector/quadtree/node')},{'1'})
        rows=self.e.encyclopedia_data({})['rows'];missile=next(r for r in rows if r['identity']=='missile_test_macro')
        tree=self.export([{'kind':'encyclopedia','id':missile['identity'],'storage':missile['group'],'value':1}])
        self.assertIsNotNone(tree.find('.//known/entries[@type="missiletypes"]/entry[@id="missile_test_macro"]'))
        self.assertIsNotNone(tree.find('.//known/entries[@type="wares"]/entry[@id="ore"]'))
        with self.assertRaises(ValueError):self.e.plan([{'kind':'encyclopedia','id':'not-real','storage':'wares','value':1}])

    def test_encyclopedia_filters_unknown_and_known_before_pagination(self):
        known=self.e.encyclopedia_data({'status':'known'})
        unknown=self.e.encyclopedia_data({'status':'unknown'})
        all_rows=self.e.encyclopedia_data({'status':'all'})
        self.assertTrue(known['rows']);self.assertTrue(unknown['rows'])
        self.assertTrue(all(r['known'] for r in known['rows']))
        self.assertTrue(all(not r['known'] for r in unknown['rows']))
        self.assertEqual(all_rows['total'],known['total']+unknown['total'])
        self.assertEqual(self.e.encyclopedia_data({'status':'unknown','search':'ore','group':'wares'})['total'],0)
        self.assertEqual(self.e.encyclopedia_data({'status':'unknown','page':1})['rows'],[])
        self.assertEqual(unknown['groups'],known['groups'])

    def test_station_settings_do_not_write_economylog_or_reference_cache(self):
        station=next(n for n in self.e.station_accounts if self.e.asset_name(n)=='Factory A')
        data=self.e.station_settings({'station':station});price=data['rows'][0];rule=data['ruleRows'][0];allocation=data['allocations'][0]
        tree=self.export([{'kind':'station_price','station':station,'id':price['id'],'storage':'buy','value':15},
                          {'kind':'station_rule','station':station,'id':rule['id'],'storage':'buy','value':5},
                          {'kind':'station_restriction','id':station,'value':'player argon'},
                          {'kind':'station_allocation','station':station,'id':allocation['id'],'storage':allocation['key'],'value':8}])
        factory=tree.find('.//component[@name="Factory A"]')
        self.assertEqual(factory.find('trade/prices/ware').get('buy'),'15')
        self.assertEqual(factory.find('trade/prices/reference/ware').get('buy'),'9')
        self.assertEqual(factory.find('traderules/wares/ware').get('buy'),'5')
        self.assertEqual(factory.find('trade/restrictions').get('factions'),'player argon')
        with self.assertRaises(ValueError):self.e.plan([{'kind':'station_price','station':station,'id':data['referenceRows'][0]['id'],'storage':'buy','value':15}])

    def test_research_resources_and_remaining_time(self):
        record=self.e.research_tasks()[0]
        tree=self.export([{'kind':'research_stock','id':'research_advanced','value':1},{'kind':'research_time','id':record['id'],'value':0}])
        hq=tree.find('.//component[@macro="station_pla_headquarters_base_01_macro"]')
        self.assertEqual(hq.find('production').get('endtime'),'100')
        self.assertEqual(hq.find('.//cargo/ware[@ware="ore"]').get('amount'),'2')
        with self.assertRaises(ValueError):self.e.plan([{'kind':'research_time','id':record['id'],'value':99999}])

    def test_roster_and_service_views_are_paginated_without_losing_counts(self):
        roster=self.e.view({'kind':'crew_roster','ship':self.e.current,'page':1})
        self.assertEqual(roster['rows'],[])
        self.assertEqual(roster['total'],2)
        self.assertEqual(roster['counts'],{'service':1,'marine':1})
        self.assertEqual(self.e.view({'kind':'ship_service','ship':self.e.current,'page':1})['rows'],[])

    def test_native_component_refs_and_ungrouped_deployables(self):
        self.e.game.wares['deploy_test'].update(component='deploy_test_macro',group=None,tags='equipment satellite')
        self.e.ammo_catalogue.cache_clear()
        self.assertEqual(self.e.game.macro_for_ware('deploy_test'),'deploy_test_macro')
        self.assertEqual(next(r for r in self.e.ammo_catalogue() if r['ware']=='deploy_test')['group'],'deployable')

    def test_sources_locate_actual_hull_fog_and_encyclopedia_records(self):
        commands=[({'kind':'repair','id':self.e.current},self.e.first(self.e.current,'hull')),
                  ({'kind':'map_reveal','id':self.e.map_data({})['selected']},self.e.map_data({})['tree'])]
        for command,node in commands:
            self.assertEqual(self.e.source_nodes(command)['nodes'][0]['id'],node)
        command={'kind':'encyclopedia','id':'ore','storage':'wares'}
        source=self.e.source_nodes(command)['nodes'][0]['id']
        self.assertEqual(self.e.names[self.e.node(source)[1]],'entry')

    def test_person_deletion_rejects_references_and_descendant_conflicts(self):
        from edits import Plan
        person=self.e.crew_roster({'ship':self.e.current})['rows'][0]['id']
        plan=Plan(self.e.folder);plan.remove_branch(person,{'person','npcseed','skills','quantity','quality'})
        skills=self.e.first(person,'skills')
        if skills:
            with self.assertRaises(ValueError):plan.compile({skills:{'piloting':'1'}})
        # No other kinds of subtrees can be deleted through the personnel path.
        with self.assertRaises(ValueError):Plan(self.e.folder).remove_branch(self.e.current,{'person','npcseed','skills'})
        source=self.root/'referenced.xml';source.write_text(EXPANSION_SAVE.replace('<person ','<person ref="linked-person" ',1),'utf-8')
        folder,_=core.build_index(source,self.root/'cache');other=Editor(folder,self.root/'game')
        try:
            person=other.crew_roster({'ship':other.current})['rows'][0]['id']
            with self.assertRaises(ValueError):Plan(folder).remove_branch(person,{'person','npcseed','skills','quantity','quality'})
        finally:other.close()

    def test_native_map_positions_are_relative_and_explicit_save_offsets_win(self):
        maps=self.root/'game/maps/xu_ep2_universe';maps.mkdir(parents=True)
        maps.joinpath('galaxy.xml').write_text('<macros><macro name="universe"><connections><connection><offset><position x="300" z="400"/></offset><macro ref="cluster"/></connection></connections></macro></macros>','utf-8')
        self.e.close();self.e=Editor(self.e.folder,self.root/'game')
        self.assertEqual(self.e.game.map_positions()[('universe','cluster')],{'x':300.,'z':400.})
        self.assertEqual((self.e.galaxy_sectors()[0]['x'],self.e.galaxy_sectors()[0]['z']),(10.,20.))

    def test_sector_dlc_source_tracks_introduction_and_preserves_unknown(self):
        from game_data import GameData
        root=self.root/'origin-game';(root/'libraries').mkdir(parents=True)
        (root/'libraries/mapdefaults.xml').write_text('<defaults><dataset macro="base_sector"><properties><identification name="Base"/></properties></dataset></defaults>','utf-8')
        for ext,name,xml in [
            ('ego_dlc_split','Test Split','<defaults><dataset macro="base_sector"><properties><identification name="Updated"/></properties></dataset><dataset macro="split_sector"><properties><identification name="Split"/></properties></dataset></defaults>'),
            ('ego_dlc_terran','Test Terran','<diff><add sel="/defaults"><dataset macro="terran_sector"><properties><identification name="Terran"/></properties></dataset></add></diff>')]:
            folder=root/'extensions'/ext;(folder/'libraries').mkdir(parents=True)
            (folder/'content.xml').write_text(f'<content name="{name}"/>','utf-8')
            (folder/'libraries/mapdefaults.xml').write_text(xml,'utf-8')
        game=GameData(root,['ego_dlc_split','ego_dlc_terran'])
        self.assertEqual(game.sector_source('base_sector'),{'id':'base','name':'基础游戏'})
        self.assertEqual(game.sectors['base_sector'],'Updated')
        self.assertEqual(game.sector_source('SPLIT_SECTOR'),{'id':'ego_dlc_split','name':'Test Split'})
        self.assertEqual(game.sector_source('terran_sector'),{'id':'ego_dlc_terran','name':'Test Terran'})
        self.assertEqual(game.sector_source('mod_sector')['id'],'unknown')
