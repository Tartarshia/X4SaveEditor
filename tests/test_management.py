import gzip
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import core
from gameplay import Editor
from test_gameplay import SAVE, make_game


MANAGEMENT_SAVE = (SAVE.replace('version="900"','version="900" time="100"')
    .replace('<faction id="player"><account', '<faction id="player"><licences><licence type="friend" factions="teladi"/></licences><account')
    .replace('<blueprints><blueprint', '<research><research ware="research_base" method="research"/></research><blueprints><blueprint')
    .replace('<component class="ship_s" id="ship" owner="player" name="Test ship">',
             '<component class="ship_s" id="ship" owner="player" name="Test ship"><modification><ship ware="mod_ship_test" mass="0.9" drag="0.98"/></modification><weapons><group group="left"><modification><weapon ware="mod_weapon_test" damage="1.1" cooling="0.8" mystery="7"/></modification></group></weapons>')
    .replace('<component class="ship_s" owner="enemy"><connections>',
             '<component class="ship_s" owner="enemy"><modification><ship ware="mod_ship_test" mass="0.9" drag="0.98"/></modification><connections>')
    .replace('<component class="ship_s" id="empty"',
             '<component class="station" owner="player" macro="station_pla_headquarters_base_01_macro" name="HQ"><account id="hq-cash"/></component><component class="ship_s" id="empty"')
    .replace('<connection><component class="production" macro="test_production"/>',
             '<connection><component class="habitation" macro="test_hab_arg"/></connection><connection><component class="habitation" macro="test_hab_bor"/></connection><connection><component class="production" macro="test_production"/>'))


def make_management_game(root):
    make_game(root)
    path=root/'libraries/wares.xml'
    path.write_text(path.read_text('utf-8').replace('</wares>','''
<ware id="ship_test" name="Test Ship Blueprint" transport="ship" tags="ship"><production/></ware>
<ware id="module_test" name="Test Module Blueprint" transport="container" tags="module"><production/></ware>
<ware id="module_blocked" name="Blocked Module" transport="container" tags="module noblueprint"><production/></ware>
<ware id="ship_blocked" name="Blocked Ship" transport="ship" tags="ship noplayerblueprint"><production/></ware>
<ware id="commodity" name="Commodity" transport="container"><production/></ware>
<ware id="mod_ship_test" name="Test Ship MOD" transport="inventory" tags="equipmentmod"/>
<ware id="mod_weapon_test" name="Test Weapon MOD" transport="inventory" tags="equipmentmod"/>
<ware id="research_base" name="Research Base" transport="research"><research time="10"/></ware>
<ware id="research_advanced" name="Research Advanced" transport="research"><research time="20"><research><ware ware="research_base"/></research></research></ware>
<ware id="research_aux" name="Research Aux" transport="research"><research time="10"/></ware>
<ware id="research_top" name="Research Top" transport="research"><research time="30"><research><ware ware="research_advanced"/><ware ware="research_aux"/></research></research></ware>
<ware id="research_hidden" name="Hidden" transport="research" tags="hidden"><research time="10"/></ware>
</wares>'''),'utf-8')
    (root/'libraries/equipmentmods.xml').write_text('''<equipmentmods>
<ship><mass ware="mod_ship_test" quality="3" min="0.75" max="0.95"><bonus chance="1" max="2"><drag min="0.8" max="1.05"/><unitcapacity min="1" max="4"/></bonus></mass></ship>
<weapon><damage ware="mod_weapon_test" quality="1" min="1.05" max="1.25"><bonus chance="1" max="1"><cooling min="0.7" max="0.9"/></bonus></damage></weapon>
</equipmentmods>''','utf-8')
    (root/'libraries/factions.xml').write_text('''<factions>
<faction id="argon" name="Argon"><licences>
<licence type="friend" name="Friend"/>
<licence type="trade" name="Trade Subscription" precursor="friend"/>
<licence type="internal" name="Internal" tags="hidden"/>
</licences></faction>
<faction id="teladi" name="Teladi"><licences><licence type="friend" name="Friend"/><licence type="trade" name="Trade" precursor="friend"/></licences></faction>
</factions>''','utf-8')
    (root/'libraries/races.xml').write_text('<races><race id="argon" name="Argon Workers"/><race id="boron" name="Boron Workers"/></races>','utf-8')
    for race,capacity in [('arg',100),('bor',50)]:
        (root/f'assets/test/macros/test_hab_{race}.xml').write_text(f'<macros><macro name="test_hab_{race}" class="habitation"><properties><workforce race="{"argon" if race=="arg" else "boron"}" capacity="{capacity}"/></properties></macro></macros>','utf-8')


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        make_management_game(self.root/'game')
        self.editor=self.open(MANAGEMENT_SAVE)

    def tearDown(self):
        self.editor.close();self.temp.cleanup()

    def open(self, raw):
        source=self.root/f'save-{len(list(self.root.glob("save-*")))}.xml'
        source.write_text(raw,'utf-8')
        folder,_=core.build_index(source,self.root/'cache')
        return Editor(folder,self.root/'game')

    def export(self, commands, editor=None):
        editor=editor or self.editor
        original=(editor.folder/'source.xml').read_bytes()
        destination=self.root/f'export-{len(list(self.root.glob("export-*")))}.xml.gz'
        editor.plan(commands).export({},destination,lambda m:None)
        self.assertEqual((editor.folder/'source.xml').read_bytes(),original)
        with gzip.open(destination,'rt',encoding='utf-8') as f:raw=f.read()
        self.assertIn("<unchanged quoted='yes'><!-- keep bytes --></unchanged>",raw)
        return ET.fromstring(raw)

    def test_ship_module_blueprints_and_group_filter(self):
        e=self.editor
        rows=e.view({'kind':'blueprints','ownership':'missing'})['rows']
        self.assertEqual({r['id'] for r in rows},{'new_engine','ship_test','module_test'})
        self.assertEqual(e.view({'kind':'blueprints','group':'ships'})['rows'][0]['id'],'ship_test')
        tree=self.export([{'kind':'blueprint','id':'ship_test'},{'kind':'blueprint','id':'module_test'},{'kind':'blueprint','id':'ship_test'}])
        self.assertEqual(len(tree.findall('.//blueprint[@ware="ship_test"]')),1)
        self.assertIsNotNone(tree.find('.//blueprint[@ware="module_test"]'))
        for wid in ('ship_blocked','module_blocked','commodity'):
            with self.subTest(wid=wid),self.assertRaises(ValueError):e.plan([{'kind':'blueprint','id':wid}])

    def test_installed_mod_ranges_best_direction_and_isolation(self):
        e=self.editor;mods=list(e.installed_mods().values())
        self.assertEqual(len(mods),2)
        hull=next(m for m in mods if m['category']=='ship')
        weapon=next(m for m in mods if m['category']=='weapon')
        self.assertEqual(next(f for f in hull['fields'] if f['id']=='mass')['best'],0.75)
        self.assertEqual(next(f for f in weapon['fields'] if f['id']=='cooling')['best'],0.9)
        self.assertFalse(next(f for f in weapon['fields'] if f['id']=='mystery')['editable'])
        tree=self.export([{'kind':'mod_value','id':m['id'],'storage':f['id'],'value':f['best']}
                          for m in mods for f in m['fields'] if f['editable']])
        self.assertEqual(tree.find('.//component[@id="ship"]/modification/ship').get('mass'),'0.75')
        self.assertEqual(tree.find('.//component[@owner="enemy"]/modification/ship').get('mass'),'0.9')
        self.assertEqual(tree.find('.//group/modification/weapon').get('mystery'),'7')
        for key,value in [('mass',0.7),('mass','NaN'),('mass','Infinity'),('unknown',1)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):e.plan([{'kind':'mod_value','id':hull['id'],'storage':key,'value':value}])
        with self.assertRaises(ValueError):
            e.plan([{'kind':'mod_value','id':weapon['id'],'storage':'mystery','value':8}])
        with self.assertRaises(ValueError):
            e.plan([{'kind':'mod_value','id':hull['id'],'storage':'mass','value':0.8}]).compile({str(hull['id']):{'drag':'1'}})

    def test_research_dependency_completion_and_cascade_revoke(self):
        tree=self.export([{'kind':'research','id':'research_top','value':1}])
        self.assertEqual({n.get('ware') for n in tree.findall('.//component[@class="player"]/research/research')},
                         {'research_base','research_advanced','research_aux','research_top'})
        complete=MANAGEMENT_SAVE.replace('<research ware="research_base" method="research"/>',
            '<research ware="research_base" method="research"/><research ware="research_advanced" method="research"/><research ware="research_aux" method="research"/><research ware="research_top" method="research"/>')
        editor=self.open(complete)
        try:
            tree=self.export([{'kind':'research','id':'research_base','value':0}],editor)
            self.assertEqual([n.get('ware') for n in tree.findall('.//component[@class="player"]/research/research')],['research_aux'])
        finally:editor.close()
        for cmds in ([{'kind':'research','id':'research_hidden','value':1}],
                     [{'kind':'research','id':'research_top','value':1},{'kind':'research','id':'research_base','value':0}]):
            with self.assertRaises(ValueError):self.editor.plan(cmds)

    def test_mod_capacity_bonus_is_integer_and_absent_bonuses_are_not_created(self):
        e=self.editor
        node=next(m['id'] for m in e.installed_mods().values() if m['category']=='ship')
        with self.assertRaises(ValueError):e.plan([{'kind':'mod_value','id':node,'storage':'unitcapacity','value':4}])
        editor=self.open(MANAGEMENT_SAVE.replace('drag="0.98"','drag="0.98" unitcapacity="2"'))
        try:
            mod=next(m for m in editor.installed_mods().values() if m['category']=='ship')
            field=next(f for f in mod['fields'] if f['id']=='unitcapacity')
            self.assertEqual((field['mode'],field['best']),('count',4))
            with self.assertRaises(ValueError):editor.plan([{'kind':'mod_value','id':mod['id'],'storage':'unitcapacity','value':1.5}])
            tree=self.export([{'kind':'mod_value','id':mod['id'],'storage':'unitcapacity','value':4}],editor)
            self.assertEqual(tree.find('.//component[@id="ship"]/modification/ship').get('unitcapacity'),'4')
        finally:editor.close()

    def test_active_research_and_missing_hq_are_guarded(self):
        editor=self.open(MANAGEMENT_SAVE.replace('<account id="hq-cash"/>','<account id="hq-cash"/><production ware="research_aux"/>'))
        try:
            self.assertTrue(next(r for r in editor.research_data({})['rows'] if r['id']=='research_aux')['active'])
            with self.assertRaises(ValueError):editor.plan([{'kind':'research','id':'research_top','value':1}])
        finally:editor.close()
        editor=self.open(MANAGEMENT_SAVE.replace('station_pla_headquarters_base_01_macro','ordinary_station'))
        try:
            with self.assertRaises(ValueError):editor.plan([{'kind':'research','id':'research_top','value':1}])
        finally:editor.close()

    def test_research_cycles_and_missing_dependencies_are_rejected(self):
        e=self.editor
        for prerequisites in (['missing_research'],['research_top']):
            e.game.research['research_base']['prerequisites']=prerequisites
            with self.subTest(prerequisites=prerequisites),self.assertRaises(ValueError):
                e.plan([{'kind':'research','id':'research_top','value':1}])

    def test_licences_grant_precursors_and_preserve_other_factions(self):
        tree=self.export([{'kind':'licence','id':'argon','storage':'trade','value':1},
                          {'kind':'licence','id':'teladi','storage':'trade','value':1}])
        licences=tree.find('.//faction[@id="player"]/licences')
        for kind in ('trade','friend'):
            self.assertEqual(set(licences.find(f'licence[@type="{kind}"]').get('factions').split()),{'argon','teladi'})
        editor=self.open(MANAGEMENT_SAVE.replace('type="friend" factions="teladi"',
            'type="friend" factions="teladi argon"').replace('</licences>','<licence type="trade" factions="argon teladi"/></licences>'))
        try:
            tree=self.export([{'kind':'licence','id':'argon','storage':'friend','value':0}],editor)
            self.assertEqual(tree.find('.//licence[@type="friend"]').get('factions'),'teladi')
            self.assertEqual(tree.find('.//licence[@type="trade"]').get('factions'),'teladi')
        finally:editor.close()
        for commands in ([{'kind':'licence','id':'argon','storage':'internal','value':1}],
                         [{'kind':'licence','id':'argon','storage':'trade','value':1},{'kind':'licence','id':'argon','storage':'friend','value':0}]):
            with self.assertRaises(ValueError):self.editor.plan(commands)

    def test_workforce_initialization_race_capacity_and_existing_timestamps(self):
        e=self.editor;station=next(n for n in e.station_accounts if e.asset_name(n)=='Factory A')
        data=e.workforce_data(station)
        self.assertEqual(data['capacity'],150)
        commands=[{'kind':'workforce','id':station,'storage':'argon','value':100},
                  {'kind':'workforce','id':station,'storage':'boron','value':50}]
        tree=self.export(commands)
        workforces=tree.find('.//component[@name="Factory A"]/workforces')
        self.assertEqual(workforces.get('lasttime'),'100')
        self.assertEqual({w.get('race'):w.get('amount') for w in workforces},{'argon':'100','boron':'50'})
        for race,value in [('argon',101),('boron',51),('split',1),('argon',-1)]:
            with self.subTest(race=race,value=value),self.assertRaises(ValueError):e.plan([{'kind':'workforce','id':station,'storage':race,'value':value}])
        editor=self.open(MANAGEMENT_SAVE.replace('<account id="station-A"',
            '<workforces lasttime="90"><workforce race="argon" amount="10"/><workforce race="boron" amount="5"/></workforces><account id="station-A"'))
        try:
            station=next(n for n in editor.station_accounts if editor.asset_name(n)=='Factory A')
            tree=self.export([{'kind':'workforce','id':station,'storage':'argon','value':0}],editor)
            self.assertEqual(tree.find('.//workforces').get('lasttime'),'90')
            self.assertEqual(tree.find('.//workforce[@race="boron"]').get('amount'),'5')
        finally:editor.close()

    def test_duplicate_research_licences_and_workforce_refuse_edits(self):
        variants=[(MANAGEMENT_SAVE.replace('<research ware="research_base" method="research"/>','<research ware="research_base" method="research"/><research ware="research_base" method="research"/>'),
                   {'kind':'research','id':'research_base','value':0}),
                  (MANAGEMENT_SAVE.replace('<licence type="friend" factions="teladi"/>','<licence type="friend" factions="teladi"/><licence type="friend" factions="argon"/>'),
                   {'kind':'licence','id':'argon','storage':'friend','value':1})]
        for raw,command in variants:
            editor=self.open(raw)
            try:
                with self.assertRaises(ValueError):editor.plan([command])
            finally:editor.close()
        editor=self.open(MANAGEMENT_SAVE.replace('<account id="station-A"',
            '<workforces><workforce race="argon" amount="1"/><workforce race="argon" amount="2"/></workforces><account id="station-A"'))
        try:
            station=next(n for n in editor.station_accounts if editor.asset_name(n)=='Factory A')
            with self.assertRaises(ValueError):editor.plan([{'kind':'workforce','id':station,'storage':'argon','value':5}])
        finally:editor.close()
        editor=self.open(MANAGEMENT_SAVE.replace('<ship ware="mod_ship_test" mass="0.9" drag="0.98"/>',
            '<ship ware="mod_ship_test" mass="0.9" drag="0.98"/><ship ware="mod_ship_test" mass="0.8" drag="0.9"/>'))
        try:
            node=next(m['id'] for m in editor.installed_mods().values() if m['category']=='ship')
            with self.assertRaises(ValueError):editor.plan([{'kind':'mod_value','id':node,'storage':'mass','value':0.75}])
        finally:editor.close()
