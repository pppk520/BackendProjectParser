import re
import logging
import json

from util.file_utility import FileUtility

from scope_parser.declare import Declare
from scope_parser.set import Set
from scope_parser.input import Input
from scope_parser.output import Output
from scope_parser.module import Module
from scope_parser.process import Process
from scope_parser.using import Using
from scope_parser.select import Select

from graph.node import Node
from graph.edge import Edge
from graph.graph_utility import GraphUtility

class ScriptParser(object):
    logger = logging.getLogger(__name__)

    def __init__(self):
        self.vars = {}

        self.declare = Declare()
        self.set = Set()
        self.input = Input()
        self.output = Output()
        self.module = Module()
        self.process = Process()
        self.using = Using()
        self.select = Select()

    def remove_empty_lines(self, content):
        return "\n".join([ll.rstrip() for ll in content.splitlines() if ll.strip()])

    def remove_comments(self, content):
        re_comment = re.compile(r'/\*(.*?)\*/', re.MULTILINE | re.DOTALL)

        # remove comments
        content = re.sub(re_comment, '', content)
        content = re.sub(r'(//.*)\n', '\n', content)

        return content

    def remove_if(self, content):
        re_if = re.compile(r'#IF.*?\n(.*?)#ENDIF', re.MULTILINE | re.DOTALL)

        content = re.sub(re_if, '\g<1>', content)

        return content

    def resolve_external_params(self, content, params={}):
        self.logger.debug('params = {}'.format(params))

        re_external_param = re.compile(r'@@(.*?)@@')

        def replace_matched(match):
            text = match.group()
            return params.get(match.group(1), text)

        return re_external_param.sub(replace_matched, content)

    def find_latest_node(self, target_name, nodes):
        for node in nodes[::-1]:
            if node.name == target_name:
                return node

        self.logger.warning('cannot find node [{}]! Probably source node.'.format(target_name))

        attr = {}
        if target_name.startswith('SSTREAM'):
            attr = {'type': 'input'}

        return Node(target_name, attr=attr)

    def upsert_node(self, node_map, node_name):
        if node_name not in node_map:
            self.logger.info('cannot find node [{}]! Probably source node.'.format(node_name))

            attr = {}
            if node_name.startswith('SSTREAM') or node_name.startswith('EXTRACT'):
                attr = {'type': 'input'}

            node_map[node_name] = Node(node_name, attr=attr)

    def remove_loop(self, content):
        re_loop = re.compile(r'LOOP\(.*\).*?{(.*?)}', re.MULTILINE | re.DOTALL)
        content = re.sub(re_loop, '\g<1>', content)

        return content

    def process_output(self, part, node_map, all_nodes, edges):
        d = self.output.parse(part)
        self.logger.debug(d)

        source_name = d['ident']
        from_node = node_map.get(source_name, node_map['last_node'])
        to_node = Node(d['path'], attr={'type': 'output'})

        edges.append(Edge(from_node, to_node))
        all_nodes.append(to_node)

    def process_extract(self, part, node_map, all_nodes, edges):
        d = self.input.parse(part)
        ident = d[0][0]
        value = 'EXTRACT_{}'.format(d[5])  # FROM [where]

        from_node = Node(value, attr={'type': 'input'})
        to_node = Node(ident)

        edges.append(Edge(from_node, to_node))

        node_map[ident] = to_node
        node_map['last_node'] = to_node

        all_nodes.append(from_node)
        all_nodes.append(to_node)

    def process_input_sstream(self, part, node_map, all_nodes, edges):
        d = self.input.parse(part)
        ident = d[0][0]
        value = 'SSTREAM_{}'.format(d[-1])

        from_node = Node(value, attr={'type': 'input'})
        to_node = Node(ident)

        edges.append(Edge(from_node, to_node))

        node_map[ident] = to_node
        node_map['last_node'] = to_node

        all_nodes.append(from_node)
        all_nodes.append(to_node)

    def process_process(self, part, node_map, all_nodes, edges):
        d = self.process.parse(part)

        from_nodes = []
        to_node = None

        for source in d['sources']:
            self.upsert_node(node_map, source)  # first, check and upsert if not in node_map
            from_nodes.append(node_map[source])

        if len(from_nodes) == 0:
            from_nodes.append(node_map['last_node'])

        if d['assign_var']:
            node_name = d['assign_var']
            new_node = Node(node_name)
            node_map[node_name] = new_node  # update
            to_node = new_node
        else:
            to_node = node_map['last_node']

        for from_node in from_nodes:
            edges.append(Edge(from_node, to_node))
            all_nodes.append(from_node)

        all_nodes.append(to_node)
        node_map['last_node'] = to_node

    def process_select(self, part, node_map, all_nodes, edges):
        d = self.select.parse(part)
        self.logger.debug(d)
        self.logger.info('[{}] = select from sources [{}]'.format(d['assign_var'], d['sources']))

        from_nodes = []
        to_node = None

        for source in d['sources']:
            self.upsert_node(node_map, source) # first, check and upsert if not in node_map
            from_nodes.append(node_map[source])

        if len(from_nodes) == 0:
            from_nodes.append(node_map['last_node'])

        if d['assign_var']:
            node_name = d['assign_var']
            new_node = Node(node_name)
            node_map[node_name] = new_node # update
            to_node = new_node
        else:
            to_node = node_map['last_node']

        for from_node in from_nodes:
            edges.append(Edge(from_node, to_node))
            all_nodes.append(from_node)

        all_nodes.append(to_node)
        node_map['last_node'] = to_node

    def process_declare(self, part, declare_map):
        key, value = self.declare.parse(part)
        declare_map[key] = value

        self.logger.info('declare [{}] as [{}]'.format(key, value))

    def process_set(self, part, declare_map):
        key, value = self.set.parse(part)
        declare_map[key] = value

        self.logger.info('set [{}] as [{}]'.format(key, value))

    def parse_file(self, filepath, external_params={}, dest_filepath=None):
        content = FileUtility.get_file_content(filepath)
#        content = self.remove_empty_lines(content)
        content = self.remove_comments(content)
        content = self.remove_if(content)
        content = self.resolve_external_params(content, external_params)
        content = self.remove_loop(content)

        parts = content.split(';')

        declare_map = {}

        node_map = {'last_node': None}
        edges = []
        all_nodes = [] # add node to networkx ourself, missing nodes in edges will be added automatically
                       # and the id of auto-added nodes are not controllable

        for part in parts:
            self.logger.debug('-' * 20)
            self.logger.debug(part)

            # ignore data after C# block
            if '#CS' in part:
                self.logger.info('meet CS block, break parsing.')
                break

            if '#DECLARE' in part:
                self.process_declare(part, declare_map)
            elif '#SET' in part:
                self.process_set(part, declare_map)
            elif 'SELECT' in part:
                self.process_select(part, node_map, all_nodes, edges)
            elif 'SSTREAM' in part and not 'OUTPUT' in part:
                self.process_input_sstream(part, node_map, all_nodes, edges)
            elif 'EXTRACT' in part:
                self.process_extract(part, node_map, all_nodes, edges)
            elif 'PROCESS' in part:
                self.process_process(part, node_map, all_nodes, edges)
            elif 'OUTPUT' in part:
                self.process_output(part, node_map, all_nodes, edges)

        self.logger.info(declare_map)

        if dest_filepath:
            self.logger.info('output GEXF to [{}]'.format(dest_filepath))
            GraphUtility().to_gexf_file(all_nodes, edges, dest_filepath)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

#    ScriptParser().parse_file('''D:\workspace\AdInsights\private\Backend\SOV\Scope\AuctionInsight\scripts\AucIns_Final.script''', dest_filepath='d:/tmp/tt.gexf')
    ScriptParser().parse_file('''D:\workspace\AdInsights\private\Backend\Opportunities\Scope\KeywordOpportunitiesV2\KeywordOpportunitiesV2/6.MPIProcessing.script''', dest_filepath='d:/tmp/tt.gexf')
#    ScriptParser().parse_file('''D:/workspace/AdInsights/private/Backend/UCM/Src/Scope/UCM_CopyTaxonomyVertical.script''', dest_filepath='d:/tmp/tt.gexf')
#    ScriptParser().parse_file('''D:\workspace\AdInsights\private\Backend\Opportunities\Scope\KeywordOpportunitiesV2\KeywordOpportunitiesV2/7.PKVGeneration_BMMO.script''', dest_filepath='d:/tmp/tt.gexf')
#    print(ScriptParser().resolve_external_params(s, {'external': 'yoyo'}))
#    print(ScriptParser().resolve_declare(s_declare))
#    ScriptParser().parse_file('../tests/files/SOV3_StripeOutput.script')
