import hashlib
from pathlib import Path
import tempfile
import unittest
import core
from gameplay import Editor
from test_management import MANAGEMENT_SAVE, make_management_game


class SourceNodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        make_management_game(root/'game')
        raw = MANAGEMENT_SAVE.replace('<research><research', '<inventory><ware ware="inv_training" amount="2"/></inventory><diplomacy influence="12"><agents><agent component="agent-npc" faction="player"/></agents></diplomacy><research><research')
        raw = raw.replace('<component class="npc" owner="player" name="Captain"><traits>', '<component class="npc" owner="player" name="Captain" id="agent-npc"><blackboard><value name="$diplomacy_exp_negotiation" type="integer" value="19"/></blackboard><traits>')
        source = root/'save.xml'
        source.write_text(raw,'utf-8')
        folder,_ = core.build_index(source,root/'cache')
        self.editor = Editor(folder,root/'game')

    def tearDown(self):
        self.editor.close()
        self.temp.cleanup()

    def test_every_command_kind_locates_original_and_linked_nodes_without_writing(self):
        e = self.editor
        station = next(n for n in e.station_accounts if e.asset_name(n)=='Factory A')
        cargo = e.cargo(e.current)[0]
        mod = next(m for m in e.installed_mods().values() if m['category']=='ship')
        agent = e.diplomacy_agents()[0]
        commands = [
            {'kind':'money','value':100},
            {'kind':'station_money','id':station,'value':100},
            {'kind':'construction_money','id':station,'value':100},
            {'kind':'station_stock','id':station,'storage':'ore','value':8},
            {'kind':'build_stock','id':station,'storage':'energycells','value':20},
            {'kind':'influence','value':30},
            {'kind':'agent_exp','id':agent['id'],'storage':'negotiation','value':100},
            {'kind':'agent_exp','id':agent['id'],'storage':'espionage','value':100},
            {'kind':'npc_relation','id':'argon','storage':'teladi','value':0.1},
            {'kind':'relation','id':'argon','value':0.1},
            {'kind':'blueprint','id':'ship_test'},
            {'kind':'crew','id':next(iter(e.crew)),'skill':'all','value':15},
            {'kind':'cargo','ship':e.current,'storage':cargo['id'],'id':'ore','value':0},
            {'kind':'cargo','ship':e.current,'storage':cargo['id'],'id':'ice','value':2},
            {'kind':'inventory','storage':e.player,'id':'inv_training','value':0},
            {'kind':'mod_value','id':mod['id'],'storage':'mass','value':0.75},
            {'kind':'research','id':'research_top','value':1},
            {'kind':'research','id':'research_base','value':0},
            {'kind':'licence','id':'argon','storage':'trade','value':1},
            {'kind':'workforce','id':station,'storage':'argon','value':100},
        ]
        path = e.folder/'source.xml'
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        for command in commands:
            with self.subTest(command=command):
                result = e.view({'kind':'source_nodes','command':command})
                ids = {row['id'] for row in result['nodes']}
                self.assertTrue(ids)
                for node in ids:
                    self.assertEqual(core.query(e.folder,'node',node)[0][0],node)
                plan = e.plan([command])
                self.assertTrue((set(plan.attrs)|set(plan.children)|plan.removed)<=ids)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

    def test_invalid_drafts_and_readonly_items_still_show_original(self):
        e = self.editor
        mod = next(iter(e.installed_mods().values()))
        result = e.source_nodes({'kind':'mod_value','id':mod['id'],'storage':'mass','value':''})
        self.assertEqual(result['nodes'][0]['id'],mod['id'])
        parent = e.first(e.player,'blueprints')
        self.assertEqual(e.source_nodes({'kind':'blueprint','id':'ship_test'})['nodes'][0]['id'],parent)
        existing = e.children(parent,'blueprint')[0]
        self.assertEqual(e.source_nodes({'kind':'blueprint','id':'old_engine'})['nodes'][0]['id'],existing)
        self.assertTrue(e.source_nodes({'kind':'relation','id':'xenon','value':''})['nodes'])
        with self.assertRaises(ValueError):e.source_nodes({'kind':'mod_value','id':99999999,'storage':'mass','value':0.75})
