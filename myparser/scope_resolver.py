import re
import logging
from datetime import datetime
from datetime import timedelta
from dateutil import parser
from scope_parser.declare_rvalue import DeclareRvalue


class ScopeResolver(object):
    logger = logging.getLogger(__name__)

    def __init__(self):
        self.dr = DeclareRvalue()
        self.default_datetime_obj = datetime.now() - timedelta(5)
        pass

    def resolve_basic(self, format_items, declare_map):
        ret = []

        datetime_obj = None

        for format_item in format_items:
            if format_item in declare_map:
                the_data = declare_map[format_item]
            else:
                if 'DateTime' in format_item:
                    the_data = self.resolve_declare_rvalue(None, format_item, declare_map)
                    datetime_obj = the_data
                elif 'AddDays' in format_item:
                    the_obj_name = format_item.split('.')[0]
                    if the_obj_name in declare_map:
                        the_obj = declare_map[the_obj_name]
                        the_data = self.process_add_days(the_obj, format_item)
                        datetime_obj = the_data

                    the_data = self.process_to_string(the_data, format_item)
                else:
                    # change
                    match = re.match('@"(.*)"', format_item)
                    if match:
                        the_data = match.group(1)
                    else:
                        the_data = format_item

            ret.append(the_data)

        # add quote for strings
        for i, item in enumerate(ret):
            try:
                _ = int(item)
            except:
                # it's string
                if not item.startswith('"') and item not in ['+', '-', '*', '/']:
                    ret[i] = '"{}"'.format(ret[i])

        to_eval = ''.join(ret)
        result = eval(to_eval)

        # final checking fot %Y %m %d
        if datetime_obj:
            result = datetime_obj.strftime(result)

        return result

    def is_time_format(self, the_str):
        if 'yyyy' in the_str: return True
        if 'MM' in the_str: return True
        if 'dd' in the_str: return True

        return False

    def to_normalized_time_format(self, the_str):
        return the_str.replace('yyyy', '%Y').replace('MM', '%m').replace('dd', '%d')

    def process_to_string(self, the_obj, func_str):
        found = re.findall('ToString\((.*?)\)', func_str)
        if found:
            if self.is_time_format(found[0]):
                return the_obj.strftime(self.to_normalized_time_format(found[0]))

            return str(the_obj)

        return the_obj

    def process_add_days(self, datetime_obj, func_str):
        found = re.findall('AddDays\((.*?)\)', func_str)
        if found:
            return datetime_obj + timedelta(int(found[0]))

        return datetime_obj

    def resolve_func(self, func_str, declare_map={}):
        params = re.findall(r'\((.*?)\)', func_str)
        param = params[0].lstrip('"').rstrip('"')

        param = declare_map.get(param, param)

        result = func_str

        if func_str.startswith('DateTime.Parse'):
            if isinstance(param, str):
                result = parser.parse(param)
            else:
                result = param
        elif func_str.startswith('int.Parse'):
            result = int(param)
        elif func_str.startswith('Math.Abs'):
            result = abs(int(param))

        if 'ToString()' in func_str:
            result = str(result)

        if 'AddDays' in func_str:
            # must be datetime already
            result = self.process_add_days(result, func_str)

        return result

    def resolve_ymd(self, fmt_str, datetime_obj):
        return datetime_obj.strftime(fmt_str)

    def resolve_str_format(self, format_str, format_items, declare_map):
        placeholders = re.findall(r'{(.*?)}', format_str)

        # resolve placeholder values
        for i, format_item in enumerate(format_items):
            format_items[i] = self.resolve_declare_rvalue(None, format_item, declare_map)

        self.logger.debug('format_items = ' + str(format_items))

        replace_map = {}
        datetime_obj = None

        for ph in placeholders:
            if ':' in ph:
                idx, fmt = ph.split(':')
                replace_to = format_items[int(idx)]

                self.logger.debug('fmt = {}, idx = {}'.format(fmt, idx))
                if 'yyyy' in fmt or 'MM' in fmt or 'dd' in fmt:
                    item = format_items[int(idx)]

                    if item in declare_map:
                        datetime_obj = declare_map[item]
                    else:
                        datetime_obj = item

                    date_Y = datetime_obj.strftime('%Y')
                    date_m = datetime_obj.strftime('%m')
                    date_d = datetime_obj.strftime('%d')

                    replace_to = fmt.replace('yyyy', date_Y).replace('MM', date_m).replace('dd', date_d)
            else:
                idx = ph
                replace_to = format_items[int(idx)]

            if not replace_to in replace_map:
                replace_map[replace_to] = []

            replace_map[replace_to].append('{' + ph + '}')

        result = format_str

        self.logger.debug('replace_map = ' + str(replace_map))

        for key in replace_map:
            if key in declare_map:
                value = declare_map[key]
            else:
                value = key

            for to_replace_str in replace_map[key]:
                result = result.replace(to_replace_str, str(value))

        # final checking fot %Y %m %d
        if datetime_obj:
            result = datetime_obj.strftime(result)

        return result

    def resolve_declare_rvalue(self, declare_lvalue, declare_rvalue, declare_map):
        self.logger.debug('resolve_declare_rvalue: declare_lvalue [{}], declare_rvalue [{}]'.format(declare_lvalue, declare_rvalue))

        try:
            ret_declare_rvalue = self.dr.parse(declare_rvalue)
        except Exception as ex:
            return declare_rvalue

        format_str = ret_declare_rvalue['format_str']
        format_items = ret_declare_rvalue['format_items']
        type_ = ret_declare_rvalue['type']

        result = ""

        # update declare_map
        if type_ == 'func_chain':
            self.logger.info('found func_chain, update declare value of [{}]'.format(declare_lvalue))
            self.logger.debug('format_items = ' + str(format_items))
            result = self.resolve_func(format_items[0], declare_map)
        elif type_ == 'format_str':
            result = self.resolve_str_format(format_str, format_items, declare_map)
        elif type_ == "str_cat":
            try:
                result = self.resolve_basic(format_items, declare_map)
            except Exception as ex:
                self.logger.warning('error resolving [{}]: {}'.format(declare_rvalue, ex))
                result = format_items[0]

        self.logger.debug('[resolve_declare_rvalue] result = ' + str(result))

        # post process to change @"str" to pure "str"
        if isinstance(result, str) and '@"' in result:
            match = re.match(r'@"(.*)"', result)
            if match:
                result = match.group(1)

        return result

    def resolve_declare(self, declare_map):
        for declare_lvalue in declare_map:
            try:
                declare_rvalue = declare_map[declare_lvalue]

                # check if it references existing param, if yes directly use it
                if declare_rvalue in declare_map:
                    declare_map[declare_lvalue] = declare_map[declare_rvalue]
                    continue

                resolved = self.resolve_declare_rvalue(declare_lvalue, declare_rvalue, declare_map)
                declare_map[declare_lvalue] = resolved
            except Exception as ex:
                # ignore unsupported syntax
                pass

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    print(ScopeResolver().resolve_declare_rvalue('',
                                                 '"/shares/bingads.algo.prod.adinsights/data/shared_data/AdvertiserEngagement/Metallica/prod/KeywordPlanner/KeywordHistoricalStatistic/Result/Daily/%Y/%m/KeywordsSearchCountDaily_%Y-%m-%d.ss?date=" + @dateObj.AddDays(-31).ToString("yyyy-MM-dd") + "..." + @dateObj.AddDays(-1).ToString("yyyy-MM-dd") + "&sparsestreamset=true"',
                                                 {'@dateObj': datetime.now()}))
