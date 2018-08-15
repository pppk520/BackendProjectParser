from pyparsing import *
from scope_parser.common import Common

class Declare(object):
    DECLARE = Keyword("#DECLARE")
    DATA_TYPE = oneOf("string String DateTime int bool double")('data_type')

    ident = Common.ident

    declare = DECLARE + Combine(ident)('key') + DATA_TYPE + '=' + restOfLine('value')

    def parse(self, s):
        data = self.declare.searchString(s)

        if data:
            return data[0][1].strip(), \
                   data[0][-1].strip().rstrip(';')

        return None, None

    def debug(self):
        s = 'string.Format(@"{0}/Preparations/MPIProcessing/{1:yyyy/MM/dd}/Campaign_TargetInfo_{1:yyyyMMdd}.ss", @KWRawPath,  DateTime.Parse(@RunDate))'
        print(s[121 - 5: 121 + 5])
        print(self.conversion_stmt.parseString(s))

if __name__ == '__main__':
    d = Declare()
    #d.debug()

    print(d.parse('#DECLARE FeatureAdoptionFilePath String = String.Format(@"{0}/{1:yyyy/MM/dd}/AccountFeatureAdoption_{1:yyyy-MM-dd}.ss", @FeatureAdoptionDataRoot, @RunDate)'))
