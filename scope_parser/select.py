from pyparsing import *
from scope_parser.common import Common
from scope_parser.input import Input
import json
import re


class Select(object):
    SELECT = Keyword("SELECT")
    FROM = Keyword("FROM")
    WHERE = Keyword("WHERE")
    JOIN = Keyword("JOIN") | Keyword("SEMIJOIN") | Keyword("PAIR JOIN") | Keyword("ANTISEMIJOIN")
    CROSS_JOIN = Keyword("CROSS JOIN")
    CROSS_APPLY = Keyword("CROSS APPLY")
    AS = Keyword("AS")
    ON = Keyword("ON")
    UNION = Keyword("UNION")
    DISTINCT = Keyword("DISTINCT")
    HAVING = Keyword("HAVING")
    IF = Keyword("IF")
    EXCEPT = Keyword("EXCEPT")
    ALL = Keyword("ALL")

    comment = Common.comment
    ident = Common.ident
    param_ident = '@' + Common.ident
    ident_dot = Common.ident_dot
    value_str = Common.value_str
    func = Common.func
    func_chain = Common.func_chain
    func_chain_logical = delimitedList(func_chain, delim=oneOf("AND OR"))
    func_chain_not = Optional('!(') + (func_chain_logical | func_chain) + Optional(')')

    cast = Combine('(' + oneOf("long ulong short int byte double") + Optional('?') + ')')
    aggr = oneOf("SUM AVG MAX MIN COUNT FIRST")
    window_over_param = 'PARTITION BY' + delimitedList(ident)

    E = CaselessLiteral("E")
    binop = oneOf("== = != < > >= <=")
    arith_sign = Word("+-", exact=1)

    # YouOrderItemId == CompOrderItemId?"You" : Domain AS Domain
    extend_ident = delimitedList(ident, delim='.', combine=True)
    ternary_condition_binop = Group(extend_ident + binop + (extend_ident | value_str))
    ternary_condition_func = func_chain
    ternary_val = extend_ident | value_str
    ternary = Optional('(') + (ternary_condition_binop | ternary_condition_func) + '?' + ternary_val + ':' + ternary_val + Optional(')')

    # AdId??0UL AS AdId
    null_coal = ident_dot + '??' + value_str

    # TOP N
    top_n = Keyword('TOP') + Word(nums)

    # Landscape.GetBidLandscape(LatestBidUSCent ?? -1, new LandscapePointSelectionConfig()).CompressCurve(LatestBidUSCent ?? -1, new CurveCompressionConfig())
    func_param_sp = null_coal | 'new' + func_chain
    func_chain_sp = ident_dot + '(' + delimitedList(func_param_sp, delim=',') + ')'
    func_chain_sp_chain = delimitedList(func_chain_sp, delim='.')

    # Math.Round(
    #                (AuctionLostToCampaignBudget_Raw - FilterReason_35_Raw) * (BudgetWinRate ?? @DefaultNativeWinRate) +
    #                FilterReason_35_Raw * (BudgetSmoothingWinRate ?? @DefaultNativeBudgetSmoothingWinRate)) AS AuctionLostToCampaignBudget
    func_as = ident_dot + '(' + Regex('(.*?)AS', re.DOTALL | re.MULTILINE)

    # IF(L.PositionNum < R.PositionNum, 0, 1) AS AboveCnt
    # IF(DailyBudgetUSD == null || MPISpend/100.0 <= DailyBudgetUSD, 1.0, DailyBudgetUSD/(MPISpend/100.0)) AS BudgetFactor
    #if_stmt = Group(IF + '(' + (ternary_condition_binop | ternary_condition_func) + ',' + value_str + ',' + value_str + ')')
    if_stmt_base = Group(IF + Regex('\(.*\)', re.DOTALL))
    if_stmt_as = Group(IF + Regex('\(.*\) AS ([^,^ ]+)', re.DOTALL))

    if_stmt = Optional(cast) + (if_stmt_as | if_stmt_base)

    and_ = Keyword("AND")
    or_ = Keyword("OR")
    in_ = Keyword("NOT IN") | Keyword("IN")

    select_stmt = Forward()
    column_name = Group(delimitedList(ident | '*', "."))

    real_num = Group(Optional(arith_sign) + (Word(nums) + "." + Optional(Word(nums)) |
                                               ("." + Word(nums))) +
                     Optional(E + Optional(arith_sign) + Word(nums)))
    int_num = Group(Optional(arith_sign) + Word(nums) +
                      Optional(E + Optional("+") + Word(nums)))
    bool_val = oneOf("true false")

    column_rval = real_num | int_num | quotedString | column_name | bool_val | param_ident # need to add support for alg expressions

    operator_ident = Group(ident + OneOrMore(oneOf('+ - * / == != >= <=') + ident))
    aggr_ident_basic = Group(aggr + '(' + (operator_ident | ident | Empty()) + ')')
    aggr_ident_operator = aggr_ident_basic + ZeroOrMore(oneOf('+ - * /') + (aggr_ident_basic | ident))
    aggr_ident_aggressive = Group(aggr + Regex('\(.*\)'))
    aggr_ident_over = aggr_ident_basic + 'OVER' + '(' + window_over_param + ')'
    aggr_ident = Optional(cast) + (aggr_ident_over | aggr_ident_operator | aggr_ident_aggressive)
    distinct_ident = DISTINCT + ident_dot
    new_something = 'new' + func_chain
    new_class_init = 'new' + ident_dot + Regex('{.*?}', re.MULTILINE | re.DOTALL)
    list_of_new_class_init = 'LIST' + '(' + new_class_init + ')'
    as_something = (AS + ident).setName('as_something')

    one_column_no_as = Optional(cast) + \
                           (distinct_ident |
                            aggr_ident |
                            ternary |
                            null_coal |
                            if_stmt |
                            new_class_init |
                            new_something |
                            list_of_new_class_init |
                            func_chain_not |
                            func_chain_sp_chain |
                            operator_ident |
                            column_name |
                            column_rval |
                            quotedString)('column_name')

    one_column_no_as_comb = delimitedList(one_column_no_as, delim='+')
    one_column = Group(one_column_no_as_comb + Optional(as_something) | '*').setName('one_column')

    one_column_anything = Word(printables + ' ', excludeChars=',\n')

    one_column_la_from = Regex(r'(.*?)(?=FROM)')
    one_column_as = (Regex(r'(.*?)AS ') | func_as) + ident  # aggresive regex for very complex column
    one_column_as_multiline = Regex(r'(.*?)AS', re.MULTILINE | re.DOTALL) + ident  # aggresive regex for very complex column, multiline version

    column_name_list = Group(delimitedList(one_column_la_from | one_column_as | one_column | one_column_as_multiline | one_column_anything))('column_name_list')
    table_name = (delimitedList(ident, ".", combine=True))("table_name")
    table_name_list = delimitedList(table_name + Optional(as_something).suppress()) # AS something, don't care
    func_expr = Combine(func + ZeroOrMore('.' + ident))

    union = Group(UNION + Optional(ALL | DISTINCT))
    except_ = Group(EXCEPT + Optional(ALL))

    where_expression = Forward()

    where_condition = Group(
        (column_name + binop + Group(column_rval)) |
        (column_name + in_ + Group("(" + delimitedList(Combine(column_rval)) + ")")) |
        (column_name + in_ + Group("(" + select_stmt + ")")) |
        ("(" + where_expression + ")")
    )
    where_expression << where_condition + ZeroOrMore((and_ | or_ | '&&' | '|') + where_expression)
    all_condition = ALL + '(' + where_condition + ZeroOrMore(',' + where_condition) + ')'

    join = Group(Optional(OneOrMore(oneOf('LEFT RIGHT OUTER INNER FULL HASH BROADCASTRIGHT'))) + JOIN)
    join_stmt = join + table_name("join_table_name*") + Optional(AS + ident) + ON + (where_expression | all_condition)
    cross_join_stmt = CROSS_JOIN + table_name("join_table_name*")
    cross_apply_stmt = CROSS_APPLY + (func_expr("cross_apply_func") | table_name) + Optional(AS + ident)

    # define the grammar
    union_select = OneOrMore(union + Optional('(') + select_stmt + Optional(')'))
    except_select = OneOrMore(except_ + Optional('(') + select_stmt + Optional(')'))
    having = HAVING + restOfLine

    from_select = Group(Optional('(') + select_stmt + Optional(')') + Optional(as_something).suppress())
    from_module = Group(Optional('(').suppress() + Input.module + Optional(')').suppress() + Optional(as_something).suppress())
    from_view = Group(Optional('(') + Input.view + Optional(')') + Optional(as_something).suppress())
    from_sstream = Group(Optional('(') + Input.sstream + Optional(')') + Optional(as_something).suppress())
    from_extract = Group(Optional('(') + Input.extract + Optional(')') + Optional(as_something).suppress())
    from_sstream_streamset = Group(Optional('(') + Input.sstream_value_streamset + Optional(')') + Optional(as_something).suppress())
    from_stmt = FROM + (from_select("from_select") |
                        from_module("module") |
                        from_view("view") |
                        from_sstream_streamset("sstream_streamset") |
                        from_sstream("sstream") |
                        from_extract("extract") |
                        table_name_list("tables"))

    select_stmt <<= (SELECT +
                     Optional(DISTINCT) +
                     Optional(top_n) +
                     (column_name_list | '*')("columns") +
                     Optional(from_stmt)("from") +
                     ZeroOrMore(join_stmt | cross_join_stmt) +
                     Optional(cross_apply_stmt) +
                     Optional(Group(WHERE + where_expression))("where") +
                     Optional(Group(union_select))('union') +
                     Optional(Group(except_select))('except_') +
                     Optional(select_stmt) +
                     Optional(having))

    select_stmt = Optional('(') + select_stmt + Optional(')') + Optional(Group(union_select))('union')

    assign_select_stmt = (Combine(ident)("assign_var") + '=' + select_stmt).ignore(comment)

    def __init__(self):
        pass

    def debug(self):
        print(self.func_as.parseString('''
            Math.Round(
               (AuctionLostToCampaignBudget_Raw - FilterReason_35_Raw) * (BudgetWinRate ?? @DefaultNativeWinRate) +
               FilterReason_35_Raw * (BudgetSmoothingWinRate ?? @DefaultNativeBudgetSmoothingWinRate)) AS
        '''))


    def parse_ternary(self, s):
        return self.ternary.parseString(s)

    def parse_if(self, s):
        return self.if_stmt.parseString(s)

    def parse_null_coal(self, s):
        return self.null_coal.parseString(s)

    def parse_cast(self, s):
        return self.cast_ident.parseString(s)

    def parse_aggr(self, s):
        return self.aggr_ident.parseString(s)

    def parse_join(self, s):
        return self.join_stmt.parseString(s)

    def parse_one_column(self, s):
        return self.one_column.parseString(s)

    def parse_select(self, s):
        return self.select_stmt.parseString(s)

    def parse_assign_select(self, s):
        return self.assign_select_stmt.parseString(s)

    def add_source(self, sources, parsed_result):
        if 'tables' in parsed_result:
            sources |= set(parsed_result['tables'])

        if 'table_name' in parsed_result:
            sources.add(parsed_result['table_name'])

        if 'join_table_name' in parsed_result:
            for table_name in parsed_result['join_table_name']:
                sources.add(table_name)

        if 'union' in parsed_result:
            self.add_source(sources, parsed_result['union'][0])

        if 'except_' in parsed_result:
            self.add_source(sources, parsed_result['except_'][0])

        if 'module' in parsed_result:
            sources.add("MODULE_{}".format(parsed_result['module'][0]['module_dotname']))

        if 'view' in parsed_result:
            sources.add("VIEW_{}".format(parsed_result['view']['from_source']))

        if 'sstream' in parsed_result:
            sources.add("SSTREAM_{}".format(parsed_result['sstream'][2]))

        if 'extract' in parsed_result:
            sources.add("EXTRACT_{}".format(parsed_result['extract']['from_source']))

        if 'sstream_streamset' in parsed_result:
            sources.add("SSTREAM<STREAMSET>_{}".format(parsed_result['sstream_streamset'][3]))

        if 'from_select' in parsed_result:
            self.add_source(sources, parsed_result['from_select'])

        if 'cross_apply_func' in parsed_result:
            sources.add("FUNC_{}".format(parsed_result['cross_apply_func']))

        return sources


    def parse(self, s):
        # specific output for our purpose
        ret = {
            'assign_var': None,
            'sources': set()
        }

        if s.strip().startswith('SELECT'):
            data = self.parse_select(s)
        else:
            # assign_select
            data = self.parse_assign_select(s)
            ret['assign_var'] = data['assign_var']

#        print('-' *20)
#        print(json.dumps(data.asDict(), indent=4))
#        print('-' *20)

        self.add_source(ret['sources'], data)

        return ret

if __name__ == '__main__':
    obj = Select()
    obj.debug()

    print(obj.parse('''
Listing_AuctionLostToCampaignBudget_Native =
    SELECT DateKey,
           HourNum,
           L.ListingId,
           MatchTypeId,
           RelationshipId,
           DistributionChannelId,
           MediumId,
           DeviceTypeId,
           FraudQualityBand,
           NetworkId,
           AuctionLostToCampaignBudget_Raw,
           FilterReason_35_Raw,
           Math.Round(
               (AuctionLostToCampaignBudget_Raw - FilterReason_35_Raw) * (BudgetWinRate ?? @DefaultNativeWinRate) +
               FilterReason_35_Raw * (BudgetSmoothingWinRate ?? @DefaultNativeBudgetSmoothingWinRate)) AS AuctionLostToCampaignBudget,
           BudgetWinRate AS DailyListingWinRate
    FROM Listing_FiltrationFunnel_Native AS L
         LEFT OUTER JOIN
             ListingWinRate_Native AS R
         ON L.ListingId == R.ListingId;
'''))


