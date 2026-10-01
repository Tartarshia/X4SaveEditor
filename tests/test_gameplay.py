import gzip
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import core
from game_data import GameData
from gameplay import Editor, agent_level

SAVE = '''<savegame><info><game version="900"/><player money="42"/></info>
<universe><factions><faction id="player"><account id="cash" amount="42"/></faction>
<faction id="argon"><relations><booster faction="player" relation="0.2" time="20"/></relations></faction>
<faction id="teladi"/><faction id="visitor"/><faction id="visitor123"/><faction id="xenon"><relations locked="1"/></faction></factions>
<component class="player" owner="player" lastcontrolled="ship"><blueprints><blueprint ware="old_engine"/></blueprints></component>
<component class="ship_s" id="ship" owner="player" name="Test ship"><account id="cash" amount="42"/>
<people><person role="service"><skills morale="2"/></person><person role="marine"/></people>
<connections><connection><component class="storage" macro="test_storage"><cargo><ware ware="ore" amount="2"/></cargo></component></connection>
<connection><component class="npc" owner="player" name="Captain"><traits><skills piloting="3"/></traits><entity post="aipilot"/></component></connection>
<connection><component class="npc" owner="player" name="New captain"/></connection>
<connection><component class="computer" owner="player"><traits><skills piloting="3"/></traits></component></connection>
<connection><component class="ship_s" owner="enemy"><connections><connection><component class="storage" macro="test_storage"><cargo><ware ware="ore" amount="99"/></cargo></component></connection></connections></component></connection>
</connections></component><component class="ship_s" id="empty" owner="player" macro="test_ship" code="SYN-001"><connections><connection><component class="storage" macro="test_storage"/></connection></connections></component>
<component class="zone" id="zone-A"><component class="station" owner="player" name="Factory A" code="ST-A"><account id="station-A" amount="75" min="20" max="100" own="1"/><trade><reservations><reservation ware="ore" amount="1"/></reservations></trade><build><resources><shortage><ware ware="ice" amount="4"/></shortage></resources></build><connections>
<connection><component class="storage" macro="test_storage"><cargo><ware ware="ore" amount="2"/></cargo></component></connection>
<connection><component class="storage" macro="test_storage"><cargo><ware ware="ore" amount="3"/></cargo></component></connection>
<connection><component class="production" macro="test_production"/></connection></connections></component>
<component class="buildstorage" owner="player"><account id="build-A" amount="30" min="10" max="40" own="1"/><build><resources><insufficient><ware ware="energycells" amount="8"/></insufficient></resources></build><connections><connection><component class="storage" macro="test_build_storage"><cargo><ware ware="energycells" amount="10"/></cargo></component></connection></connections></component></component>
<component class="zone" id="zone-B"><component class="station" owner="player" name="Factory B" code="ST-B"><account id="station-B" own="1"/><connections><connection><component class="storage" macro="test_storage"/></connection></connections></component><component class="buildstorage" owner="player"><account id="build-B" own="1"/></component></component>
<component class="station" owner="enemy" name="Enemy Factory"><account id="enemy-cash" amount="600"/></component>
</universe><stats><stat id="money_player" value="42"/></stats><unchanged quoted='yes'><!-- keep bytes --></unchanged></savegame>'''

DIPLOMACY_SAVE = (SAVE.replace('<component class="player" owner="player" lastcontrolled="ship"><blueprints>',
    '<component class="player" owner="player" lastcontrolled="ship"><diplomacy influence="12"><agents><agent component="agent-npc" faction="player"/></agents></diplomacy><blueprints>')
    .replace('<component class="npc" owner="player" name="Captain"><traits>',
    '<component class="npc" owner="player" name="Captain" id="agent-npc"><blackboard><value name="$diplomacy_exp_negotiation" type="integer" value="19"/><value name="$diplomacy_exp_espionage" type="integer" value="49"/></blackboard><traits>'))


SECTOR_SAVE = '''<savegame><info><player money="42"/></info><universe>
<component class="player" owner="player" lastcontrolled="docked"/>
<component class="sector" macro="sector_a"><connections><connection><component class="zone">
<connections><connection><component class="ship_l" owner="player" id="carrier" name="Carrier">
<connections><connection><component class="dockingbay"><connections><connection>
<component class="ship_s" owner="player" id="docked" name="Docked"><people><person role="marine"><skills morale="3"/></person></people></component>
</connection></connections></component></connection></connections></component></connection>
<connection><component class="station" owner="player" name="Station"><connections><connection>
<component class="npc" owner="player" name="Manager"><traits><skills management="6"/></traits></component>
</connection></connections></component></connection></connections></component></connection></connections></component>
<component class="sector" macro="SECTOR_B"><connections><connection>
<component class="ship_s" owner="player" id="other" name="Other"><people><person role="service"><skills morale="6"/></person></people></component>
</connection></connections></component>
<component class="ship_s" owner="player" id="unknown" name="Unknown"><people><person role="service"/></people></component>
</universe></savegame>'''


def make_game(root):
    files = {
        'version.dat':'900',
        'libraries/wares.xml':'''<wares>
<ware id="ore" name="{1,1}" transport="solid" volume="10"/>
<ware id="ice" name="{1,2}" transport="solid" volume="5"/>
<ware id="energycells" name="Energy" transport="container" volume="1"/>
<ware id="old_engine" name="Old" transport="equipment" group="engines"><production/></ware>
<ware id="new_engine" name="{1,3}" transport="equipment" group="engines"><production/></ware>
<ware id="blocked" name="Blocked" transport="equipment" tags="noplayerblueprint"><production/></ware>
</wares>''',
        'libraries/factions.xml':'<factions><faction id="argon" name="{1,4}"/></factions>',
        'libraries/mapdefaults.xml':'<defaults><dataset macro="Sector_A"><properties><identification name="测试星区甲"/></properties></dataset><dataset macro="sector_b"><properties><identification name="测试星区乙"/></properties></dataset></defaults>',
        't/0001-l086.xml':'<language><page id="1"><t id="1">矿石</t><t id="2">冰</t><t id="3">测试引擎</t><t id="4">测试联邦</t><t id="5">测试运输舰</t></page></language>',
        'assets/test/macros/test_ship.xml':'<macros><macro name="test_ship"><properties><identification name="{1,5}"/></properties></macro></macros>',
        'assets/test/macros/test_storage.xml':'<macros><macro><properties><cargo max="100" tags="solid"/></properties></macro></macros>',
        'assets/test/macros/test_build_storage.xml':'<macros><macro><properties><cargo max="100" tags="container"/></properties></macro></macros>',
        'assets/test/macros/test_production.xml':'<macros><macro name="test_production"><properties><identification name="Test Production"/></properties></macro></macros>',
    }
    for relative,text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,'utf-8')


class GameplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root/'source.xml'
        self.source.write_text(SAVE,'utf-8')
        self.folder,_ = core.build_index(self.source,self.root/'cache')
        make_game(self.root/'game')
        self.editor = Editor(self.folder,self.root/'game')

    def tearDown(self):
        self.editor.close()
        self.temp.cleanup()

    def export(self,commands,advanced=None):
        dest = self.root/'export.xml.gz'
        self.editor.plan(commands).export(advanced or {},dest,lambda m:None)
        self.assertEqual(self.source.read_text('utf-8'),SAVE)
        with gzip.open(dest,'rt',encoding='utf-8') as f:
            raw = f.read()
        self.assertIn("<unchanged quoted='yes'><!-- keep bytes --></unchanged>",raw)
        return ET.fromstring(raw)

    def test_full_workflow(self):
        e=self.editor
        cargo=e.cargo(e.current)[0]
        crew=list(e.crew)
        station_a=next(n for n in e.station_accounts if e.asset_name(n)=='Factory A')
        station_b=next(n for n in e.station_accounts if e.asset_name(n)=='Factory B')
        self.assertEqual(len(crew),4)  # Computers and enemy ship excluded.
        tree=self.export([
            {'kind':'money','value':'123456'},
            {'kind':'station_money','id':station_a,'value':'900'},
            {'kind':'station_money','id':station_b,'value':'50'},
            {'kind':'construction_money','id':station_a,'value':'700'},
            {'kind':'construction_money','id':station_b,'value':'60'},
            {'kind':'station_stock','id':station_a,'storage':'ore','value':'12'},
            {'kind':'build_stock','id':station_a,'storage':'energycells','value':'50'},
            {'kind':'station_stock','id':station_b,'storage':'ore','value':'5'},
            {'kind':'relation','id':'argon','value':'0.1'},
            {'kind':'relation','id':'teladi','value':'0'},
            {'kind':'blueprint','id':'new_engine'},
            {'kind':'blueprint','id':'new_engine'},
            {'kind':'cargo','ship':e.current,'storage':cargo['id'],'id':'ore','value':'0'},
            {'kind':'cargo','ship':e.current,'storage':cargo['id'],'id':'ice','value':'20'},
            *[{'kind':'crew','id':n,'skill':'all','value':'15'} for n in crew]])
        self.assertEqual({a.get('amount') for a in tree.findall('.//account[@id="cash"]')},{'123456'})
        self.assertEqual(tree.find('.//account[@id="station-A"]').get('amount'),'900')
        self.assertEqual(tree.find('.//account[@id="station-A"]').get('min'),'20')
        self.assertEqual(tree.find('.//account[@id="station-A"]').get('max'),'100')
        self.assertEqual(tree.find('.//account[@id="station-B"]').get('amount'),'50')
        self.assertEqual(tree.find('.//account[@id="build-A"]').get('amount'),'700')
        self.assertEqual(tree.find('.//account[@id="build-A"]').get('min'),'10')
        self.assertEqual(tree.find('.//account[@id="build-A"]').get('max'),'40')
        self.assertEqual(tree.find('.//account[@id="build-B"]').get('amount'),'60')
        station_a_xml=tree.find('.//component[@name="Factory A"]')
        self.assertEqual([w.get('amount') for w in station_a_xml.findall('.//component[@class="storage"]/cargo/ware[@ware="ore"]')],['9','3'])
        self.assertEqual(tree.find('.//component[@class="buildstorage"]/connections/connection/component/cargo/ware').get('amount'),'50')
        station_b_xml=tree.find('.//component[@name="Factory B"]')
        self.assertEqual(station_b_xml.find('.//component[@class="storage"]/cargo/ware').get('amount'),'5')
        self.assertEqual(tree.find('.//account[@id="enemy-cash"]').get('amount'),'600')
        self.assertEqual(tree.find('info/player').get('money'),'123456')
        self.assertEqual(tree.find('stats/stat').get('value'),'123456')
        faction=tree.find('.//faction[@id="player"]')
        self.assertEqual(len(faction.findall('relations')),1)
        self.assertEqual(len(faction.findall('relations/relation')),2)
        self.assertEqual(tree.find('.//faction[@id="argon"]/relations/booster').get('relation'),'0')
        self.assertEqual(len(tree.findall('.//blueprint[@ware="new_engine"]')),1)
        ship=tree.find('.//component[@id="ship"]')
        storage=ship.find('connections/connection/component[@class="storage"]')
        self.assertEqual([(w.get('ware'),w.get('amount')) for w in storage.findall('cargo/ware')],[('ice','20')])
        self.assertEqual(tree.find('.//component[@owner="enemy"]//ware').get('amount'),'99')
        self.assertEqual(ship.find('people/person/skills').get('management'),'15')
        self.assertEqual(ship.findall('people/person')[1].find('skills').get('boarding'),'15')
        npc=tree.find('.//component[@name="New captain"]')
        self.assertEqual(npc.find('traits/skills').get('morale'),'15')
        self.assertEqual(tree.find('.//component[@class="computer"]/traits/skills').get('piloting'),'3')

    def test_empty_storage_and_missing_blueprints(self):
        e=self.editor
        ship=next(n for n,a in e.ships.items() if a.get('id')=='empty')
        storage=e.cargo(ship)[0]
        tree=self.export([{'kind':'cargo','ship':ship,'storage':storage['id'],'id':'ice','value':'1'}])
        self.assertEqual(tree.find('.//component[@id="empty"]//cargo/ware').get('amount'),'1')

    def test_validation_and_aggregate_capacity(self):
        e=self.editor
        storage=e.cargo(e.current)[0]['id']
        def cargo(w,v):return {'kind':'cargo','ship':e.current,'storage':storage,'id':w,'value':v}
        bad = [[cargo('ice',17)],[cargo('energycells',1)],[cargo('unknown',1)],
               [{'kind':'blueprint','id':'blocked'}],[{'kind':'relation','id':'xenon','value':1}],
               [{'kind':'relation','id':'argon','value':'NaN'}],
               [{'kind':'money','value':-1}],[{'kind':'money','value':1.5}],
               [{'kind':'station_money','id':999999999,'value':100}],
               [{'kind':'station_money','id':next(iter(e.station_accounts)),'value':-1}],
               [{'kind':'construction_money','id':999999999,'value':100}],
               [{'kind':'construction_money','id':next(iter(e.station_accounts)),'value':-1}],
               [{'kind':'station_stock','id':999999999,'storage':'ore','value':1}],
               [{'kind':'station_stock','id':next(iter(e.station_accounts)),'storage':'ore','value':21}],
               [{'kind':'build_stock','id':next(iter(e.station_accounts)),'storage':'ore','value':1}],
               [{'kind':'crew','id':next(iter(e.crew)),'value':16}]]
        for commands in bad:
            with self.subTest(commands=commands),self.assertRaises(ValueError):e.plan(commands).compile()
        e.plan([cargo('ore',0),cargo('ice',20)]).compile()

    def test_station_account_listing_and_zero_balance(self):
        e=self.editor
        data=e.view({'kind':'station_money'})
        self.assertEqual(data['total'],2)
        rows={r['name']:r for r in data['rows']}
        self.assertEqual(rows['Factory A']['amount'],75)
        self.assertEqual(rows['Factory B']['amount'],0)
        self.assertTrue(all(r['editable'] and r['construction']['editable'] for r in rows.values()))
        self.assertEqual(rows['Factory A']['construction']['amount'],30)
        self.assertEqual(rows['Factory B']['construction']['amount'],0)
        self.assertEqual((rows['Factory A']['min'],rows['Factory A']['max']),(20,100))
        self.assertEqual((rows['Factory A']['construction']['min'],rows['Factory A']['construction']['max']),(10,40))
        self.assertIsNone(rows['Factory B']['construction']['min'])
        self.assertEqual(e.view({'kind':'station_money','search':'ST-B'})['total'],1)
        self.assertEqual(e.view({'kind':'station_money','search':'Enemy'})['total'],0)
        self.assertEqual(e.view({'kind':'home'})['stationCount'],2)

    def test_buildstorage_must_be_uniquely_associated(self):
        source=self.root/'ambiguous.xml'
        source.write_text(SAVE.replace('<component class="buildstorage" owner="player"><account id="build-A"',
                                      '<component class="buildstorage" owner="player"><account id="build-extra"/></component><component class="buildstorage" owner="player"><account id="build-A"'),'utf-8')
        folder,_=core.build_index(source,self.root/'cache')
        editor=Editor(folder,self.root/'game')
        try:
            row=next(r for r in editor.view({'kind':'station_money'})['rows'] if r['name']=='Factory A')
            self.assertFalse(row['construction']['editable'])
            with self.assertRaises(ValueError):editor.plan([{'kind':'construction_money','id':row['id'],'value':100}])
            self.assertTrue(row['editable'])
        finally:
            editor.close()

    def test_station_resources_are_separate_from_build_storage(self):
        data=self.editor.view({'kind':'station_resources'})
        stations={r['name']:r['id'] for r in data['stations']}
        self.assertEqual(set(stations),{'Factory A','Factory B'})
        data=self.editor.view({'kind':'station_resources','station':stations['Factory A']})
        self.assertEqual(len(data['ordinary']),2)
        self.assertEqual([(w['id'],w['amount']) for w in data['ordinaryWares']],[('ore',5)])
        self.assertEqual([(w['id'],w['amount']) for w in data['buildingWares']],[('energycells',10)])
        self.assertEqual(data['production'][0]['count'],1)
        self.assertEqual({(r['kind'],r['id'],r['amount']) for r in data['ordinaryIndicators']},{('交易预留','ore',1),('记录的短缺','ice',4)})
        self.assertEqual([(r['id'],r['amount']) for r in data['buildingIndicators']],[('energycells',8)])
        self.assertEqual(self.editor.view({'kind':'station_resources','station':stations['Factory B']})['building'],[])

    def test_station_stock_combined_capacity_and_missing_build_storage(self):
        e=self.editor
        a=next(n for n in e.station_accounts if e.asset_name(n)=='Factory A')
        b=next(n for n in e.station_accounts if e.asset_name(n)=='Factory B')
        for commands in (
            [{'kind':'station_stock','id':a,'storage':'ore','value':15},
             {'kind':'station_stock','id':a,'storage':'ice','value':15}],
            [{'kind':'build_stock','id':b,'storage':'energycells','value':1}],
            [{'kind':'station_stock','id':a,'storage':'unknown','value':1}],
        ):
            with self.subTest(commands=commands),self.assertRaises(ValueError):
                e.plan(commands).compile()

    def test_diplomacy_influence_agent_levels_and_faction_pair(self):
        self.assertEqual([agent_level(x) for x in (0,9,10,19,20,49,50,99,100,199,200,999)],
                         [0,0,1,1,2,2,3,3,4,4,5,5])
        source=self.root/'diplomacy.xml';source.write_text(DIPLOMACY_SAVE,'utf-8')
        folder,_=core.build_index(source,self.root/'cache')
        editor=Editor(folder,self.root/'game')
        try:
            data=editor.view({'kind':'diplomacy','source':'argon','target':'teladi'})
            self.assertEqual(data['influence'],12)
            self.assertEqual(len(data['agents']),1)
            agent=data['agents'][0]
            self.assertTrue(agent['editable'])
            self.assertEqual(agent['levels'],{'negotiation':1,'espionage':2})
            self.assertIsNone(data['pair']['forward']['base'])
            dest=self.root/'diplomacy-export.xml.gz'
            editor.plan([{'kind':'influence','value':300},
                         {'kind':'agent_exp','id':agent['id'],'storage':'negotiation','value':100},
                         {'kind':'agent_exp','id':agent['id'],'storage':'espionage','value':200},
                         {'kind':'npc_relation','id':'argon','storage':'teladi','value':0.1}]).export({},dest,lambda m:None)
            with gzip.open(dest,'rt',encoding='utf-8') as f:tree=ET.fromstring(f.read())
            self.assertEqual(tree.find('.//component[@class="player"]/diplomacy').get('influence'),'300')
            values={n.get('name'):n.get('value') for n in tree.findall('.//component[@id="agent-npc"]/blackboard/value')}
            self.assertEqual(values['$diplomacy_exp_negotiation'],'100')
            self.assertEqual(values['$diplomacy_exp_espionage'],'200')
            self.assertEqual(tree.find('.//faction[@id="argon"]/relations/relation[@faction="teladi"]').get('relation'),'0.1')
            self.assertEqual(tree.find('.//faction[@id="teladi"]/relations/relation[@faction="argon"]').get('relation'),'0.1')
            for bad in ([{'kind':'npc_relation','id':'argon','storage':'xenon','value':1}],
                        [{'kind':'agent_exp','id':agent['id'],'storage':'negotiation','value':-1}],
                        [{'kind':'agent_exp','id':agent['id'],'storage':'negotiation','value':201}],
                        [{'kind':'influence','value':301}],
                        [{'kind':'influence','value':'NaN'}]):
                with self.subTest(bad=bad),self.assertRaises(ValueError):editor.plan(bad).compile()
        finally:editor.close()

    def test_missing_agent_experience_can_be_added_once(self):
        source=self.root/'missing-agent-exp.xml'
        source.write_text(DIPLOMACY_SAVE.replace('<value name="$diplomacy_exp_espionage" type="integer" value="49"/>',''),'utf-8')
        folder,_=core.build_index(source,self.root/'cache')
        editor=Editor(folder,self.root/'game')
        try:
            agent=editor.view({'kind':'diplomacy'})['agents'][0]
            self.assertEqual(agent['experience']['espionage'],0)
            dest=self.root/'added-agent-exp.xml.gz'
            editor.plan([{'kind':'agent_exp','id':agent['id'],'storage':'espionage','value':50}]).export({},dest,lambda m:None)
            with gzip.open(dest,'rt',encoding='utf-8') as f:tree=ET.fromstring(f.read())
            self.assertEqual(tree.find('.//component[@id="agent-npc"]/blackboard/value[@name="$diplomacy_exp_espionage"]').get('value'),'50')
        finally:editor.close()

    def test_buildstorage_requires_a_zone(self):
        source=self.root/'no-zone.xml'
        source.write_text(SAVE.replace('class="zone" id="zone-A"','class="collection" id="zone-A"'),'utf-8')
        folder,_=core.build_index(source,self.root/'cache')
        editor=Editor(folder,self.root/'game')
        try:
            rows={r['name']:r for r in editor.view({'kind':'station_money'})['rows']}
            self.assertFalse(rows['Factory A']['construction']['editable'])
            self.assertTrue(rows['Factory B']['construction']['editable'])
        finally:
            editor.close()

    def test_buildstorage_requires_one_station_in_zone(self):
        source=self.root/'two-stations.xml'
        source.write_text(SAVE.replace('<component class="buildstorage" owner="player"><account id="build-A"',
                                      '<component class="station" owner="player" name="Extra"><account id="extra"/></component><component class="buildstorage" owner="player"><account id="build-A"'),'utf-8')
        folder,_=core.build_index(source,self.root/'cache')
        editor=Editor(folder,self.root/'game')
        try:
            rows={r['name']:r for r in editor.view({'kind':'station_money'})['rows']}
            self.assertFalse(rows['Factory A']['construction']['editable'])
            self.assertFalse(rows['Extra']['construction']['editable'])
            self.assertEqual(editor.view({'kind':'station_resources','station':rows['Factory A']['id']})['building'],[])
        finally:
            editor.close()

    def test_shared_station_account_is_not_independent(self):
        source=self.root/'shared.xml';source.write_text(SAVE.replace('id="station-B"','id="station-A"'),'utf-8')
        folder,_=core.build_index(source,self.root/'cache')
        editor=Editor(folder,self.root/'game')
        try:
            rows=editor.view({'kind':'station_money'})['rows']
            self.assertEqual(len(rows),2)
            self.assertTrue(all(not row['editable'] for row in rows))
            for row in rows:
                with self.assertRaises(ValueError):editor.plan([{'kind':'station_money','id':row['id'],'value':50}])
        finally:
            editor.close()

    def test_conflict_and_last_edit_wins(self):
        e=self.editor;n=next(iter(e.crew));skill=e.crew[n]['skill_node']
        with self.assertRaises(ValueError):
            e.plan([{'kind':'crew','id':n,'skill':'all','value':15}]).compile({str(skill):{'morale':'1'}})
        tree=self.export([{'kind':'crew','id':n,'skill':'all','value':15},{'kind':'crew','id':n,'skill':'morale','value':3}])
        self.assertEqual(tree.find('.//person/skills').get('morale'),'3')
        self.assertEqual(tree.find('.//person/skills').get('engineering'),'15')

    def test_names_ownership_and_pagination(self):
        e=self.editor
        self.assertEqual(e.game.name('ore'),'矿石')
        missing=e.view({'kind':'blueprints','ownership':'missing'})
        self.assertEqual([r['id'] for r in missing['rows']],['new_engine'])
        self.assertEqual(e.view({'kind':'blueprints','search':'测试'})['total'],1)
        self.assertEqual(e.view({'kind':'crew','page':1})['rows'],[])
        self.assertEqual(e.view({'kind':'home'})['money'],'42')

    def test_visitor_factions_hidden_by_default(self):
        e=self.editor
        data=e.view({'kind':'relations'})
        self.assertEqual(data['internalCount'],2)
        self.assertEqual({r['id'] for r in data['rows']},{'argon','teladi','xenon'})
        self.assertEqual(e.view({'kind':'relations','search':'visitor'})['total'],0)
        self.assertEqual(e.view({'kind':'relations','search':'visitor','includeInternal':True})['total'],2)
        self.assertEqual(e.view({'kind':'relations','includeInternal':True})['total'],5)

    def test_no_changes_byte_identity(self):
        path=self.root/'copy.xml'
        self.editor.plan([]).export({},path,lambda m:None)
        self.assertEqual(path.read_bytes(),self.source.read_bytes())

    def test_ship_model_names_preserve_custom_names(self):
        e=self.editor
        ships=e.view({'kind':'home'})['ships']
        unnamed=next(s for s in ships if s['code']=='SYN-001')
        self.assertEqual(unnamed['name'],'测试运输舰')
        self.assertEqual(e.asset_name(e.current),'Test ship')
        self.assertEqual(e.game.model_name('TEST_SHIP'),'测试运输舰')
        self.assertEqual(e.game.model_name('missing_macro'),'未知型号（missing_macro）')
        self.assertEqual(e.game.model_name(''),'未知型号')

    def test_model_name_official_patch_and_ware_fallback(self):
        game=self.root/'game'
        ext=game/'extensions/ego_dlc_test/assets/test/macros'
        ext.mkdir(parents=True)
        (ext/'test_ship.xml').write_text('<diff><replace sel="/macros/macro[@name=\'test_ship\']/properties/identification/@name">Patched model</replace></diff>','utf-8')
        library=game/'libraries/wares.xml'
        library.write_text(library.read_text('utf-8').replace('</wares>','<ware id="fallback" name="Fallback model"><component ref="fallback_macro"/></ware></wares>'),'utf-8')
        data=GameData(game,('ego_dlc_test',))
        self.assertEqual(data.model_name('test_ship'),'Patched model')
        self.assertEqual(data.model_name('fallback_macro'),'Fallback model')

    def test_additive_dlc_sector_catalogues(self):
        game=self.root/'game'
        for ext,text in [
            ('ego_dlc_a','<defaults><dataset macro="sector_c"><properties><identification name="第三星区"/></properties></dataset><dataset macro="sector_a"><properties><identification description="new description"/></properties></dataset></defaults>'),
            ('ego_dlc_b','<defaults><dataset macro="sector_d"><properties><identification name="第四星区"/></properties></dataset></defaults>'),
            ('ego_dlc_c','<diff><replace sel="/defaults/dataset[@macro=\'Sector_A\']/properties/identification/@name">改名星区</replace></diff>')]:
            directory=game/'extensions'/ext/'libraries';directory.mkdir(parents=True)
            (directory/'mapdefaults.xml').write_text(text,'utf-8')
        data=GameData(game,('ego_dlc_a','ego_dlc_b'))
        self.assertEqual(data.sectors,{'sector_a':'测试星区甲','sector_b':'测试星区乙','sector_c':'第三星区','sector_d':'第四星区'})
        patched=GameData(game,('ego_dlc_a','ego_dlc_b','ego_dlc_c'))
        self.assertEqual(patched.sectors['sector_a'],'改名星区')
        self.assertEqual(len(patched.sectors),4)

    def test_language_comments_references_and_literal_parentheses(self):
        data=self.editor.game
        data.texts.update({('9','1'):'{9,2}(English comment)',
                           ('9','2'):'English | 中文(nested (comment))',
                           ('9','3'):r'{9,4}(ignored)',('9','4'):r'名称\(显示括号\)',
                           ('9','5'):'{9,6}',('9','6'):'{9,5}'})
        self.assertEqual(data.translate('{9,1}'),'English | 中文')
        self.assertEqual(data.translate('{9,3}'),'名称(显示括号)')
        self.assertEqual(data.translate('我的船(保留自定义名称)'),'我的船(保留自定义名称)')
        self.assertEqual(data.translate('{9,999}'),'{9,999}')
        self.assertEqual(data.translate('{9,5}'),'{9,5}')

    def test_dlc_english_does_not_override_chinese_fallback(self):
        game=self.root/'game'
        directory=game/'extensions/ego_dlc_test/t';directory.mkdir(parents=True)
        (directory/'0001-l044.xml').write_text('<language><page id="1"><t id="1">English ore</t><t id="99">English fallback(comment)</t></page></language>','utf-8')
        data=GameData(game,('ego_dlc_test',))
        self.assertEqual(data.translate('{1,1}'),'矿石')
        self.assertEqual(data.translate('{1,99}'),'English fallback')

    def test_sector_ancestry_counts_and_crew_filter(self):
        source=self.root/'sectors.xml';source.write_text(SECTOR_SAVE,'utf-8')
        folder,_=core.build_index(source,self.root/'cache')
        editor=Editor(folder,self.root/'game')
        try:
            home=editor.view({'kind':'home'})
            ships={s['name']:s for s in home['ships']}
            a=ships['Docked']['sector'];b=ships['Other']['sector']
            self.assertEqual(a,ships['Carrier']['sector'])
            self.assertEqual(a['name'],'测试星区甲')
            self.assertEqual(b['name'],'测试星区乙')
            self.assertEqual(ships['Unknown']['sector']['id'],'unknown')
            counts={r['id']:r for r in home['sectors']}
            self.assertEqual((counts[a['id']]['ships'],counts[a['id']]['crew']),(2,2))
            self.assertEqual(editor.view({'kind':'crew','sector':a['id']})['total'],2)
            self.assertEqual(editor.view({'kind':'crew','sector':b['id']})['total'],1)
            self.assertEqual(editor.view({'kind':'crew','sector':'unknown'})['total'],1)
            self.assertEqual(editor.view({'kind':'crew','sector':a['id'],'ship':ships['Other']['id']})['total'],0)
            self.assertEqual(editor.view({'kind':'crew','sector':a['id'],'ship':ships['Docked']['id']})['total'],1)
        finally:
            editor.close()

    def test_game_cat_and_dlc_diff(self):
        game=self.root/'archive-game';game.mkdir()
        ware=b'<wares><ware id="base" name="Base" transport="solid" volume="1"/></wares>'
        (game/'01.cat').write_text(f'libraries/wares.xml {len(ware)} 0 abc\n','utf-8')
        (game/'01.dat').write_bytes(ware)
        ext=game/'extensions/ego_dlc_test/libraries';ext.mkdir(parents=True)
        (ext/'wares.xml').write_text('<diff><add sel="/wares"><ware id="dlc" name="DLC" transport="equipment"><production/></ware></add><replace sel="/wares/ware[@id=\'base\']/@volume">2</replace></diff>','utf-8')
        data=GameData(game,('ego_dlc_test',))
        self.assertEqual(data.wares['base']['volume'],2)
        self.assertTrue(data.wares['dlc']['blueprint'])
        self.assertNotIn('dlc',GameData(game).wares)


if __name__=='__main__':unittest.main()
