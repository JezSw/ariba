import os
import openpyxl
import pyfastaq
from ariba import report, flag

class Error (Exception): pass

class ReportFilter:
    def __init__(self,
            infile=None,
            min_pc_ident=90,
            min_ref_base_assembled=1,
            ignore_not_has_known_variant=True,
            exclude_flags=None,
        ):

        if infile is not None:
            self.report = self._load_report(infile)
        else:
            self.report = {}

        self.min_pc_ident = min_pc_ident
        self.min_ref_base_assembled = min_ref_base_assembled
        self.ignore_not_has_known_variant = ignore_not_has_known_variant

        if exclude_flags is None:
            self.exclude_flags = ['assembly_fail', 'ref_seq_choose_fail']
        else:
            self.exclude_flags = exclude_flags


    @classmethod
    def _report_line_to_dict(cls, line):
        '''Takes report line string as input. Returns a dict of column name -> value in line'''
        data = line.split('\t')
        if len(data) != len(report.columns):
            return None

        d = dict(zip(report.columns, data))
        for key in report.int_columns:
            try:
                d[key] = int(d[key])
            except:
                assert d[key] == '.'

        for key in report.float_columns:
            try:
                d[key] = float(d[key])
            except:
                assert d[key] == '.'

        d['flag'] = flag.Flag(int(d['flag']))
        return d


    @classmethod
    def _dict_to_report_line(cls, report_dict):
        '''Takes a report_dict as input and returns a report line'''
        return '\t'.join([str(report_dict[x]) for x in report.columns])


    @staticmethod
    def _load_report(infile):
        '''Loads report file into a dictionary. Key=refrence name.
        Value = list of report lines for that reference'''
        report_dict = {}
        f = pyfastaq.utils.open_file_read(infile)
        first_line = True

        for line in f:
            line = line.rstrip()

            if first_line:
                expected_first_line = '#' + '\t'.join(report.columns)
                if line != expected_first_line:
                    pyfastaq.utils.close(f)
                    raise Error('Error reading report file. Expected first line of file is\n' + expected_first_line + '\nbut got:\n' + line)
                first_line = False
            else:
                line_dict = ReportFilter._report_line_to_dict(line)
                if line_dict is None:
                    pyfastaq.utils.close(f)
                    raise Error('Error reading report file. Expected ' + str(len(report.columns)) + ' columns but got ' + str(len(data)) + ' columns at this line:\n' + line)
                ref_name = line_dict['ref_name']
                ctg_name = line_dict['ctg']
                if ref_name not in report_dict:
                    report_dict[ref_name] = {}
                if ctg_name not in report_dict[ref_name]:
                    report_dict[ref_name][ctg_name] = []

                report_dict[ref_name][ctg_name].append(line_dict)

        pyfastaq.utils.close(f)
        return report_dict


    @staticmethod
    def _flag_passes_filter(flag, exclude_flags):
        for f in exclude_flags:
            if flag.has(f):
                return False
        return True


    def _report_dict_passes_filters(self, report_dict):
        return self._report_dict_passes_essential_filters(report_dict) and self._report_dict_passes_non_essential_filters(report_dict)


    def _report_dict_passes_non_essential_filters(self, report_dict):

        if self.ignore_not_has_known_variant:
            return report_dict['has_known_var'] == '1'
        else:
            return True


    def _report_dict_passes_essential_filters(self, report_dict):
        return ReportFilter._flag_passes_filter(report_dict['flag'], self.exclude_flags) \
                   and report_dict['pc_ident'] >= self.min_pc_ident \
                   and report_dict['ref_base_assembled'] >= self.min_ref_base_assembled \


    def _filter_list_of_dicts(self, dicts_list):
        if len(dicts_list) == 0:
            return []

        pass_dicts = []
        essential_dicts = []
        fail_dicts = []

        for d in dicts_list:
            if self._report_dict_passes_essential_filters(d):
                if self._report_dict_passes_non_essential_filters(d):
                    pass_dicts.append(d)
                else:
                    essential_dicts.append(d)
            else:
                fail_dicts.append(d)

        if len(pass_dicts) == 0:
            assert len(fail_dicts) + len(essential_dicts) > 0
            if len(essential_dicts) > 0:
                new_d = essential_dicts[0]
                for key in report.var_columns:
                    new_d[key] = '.'
                pass_dicts.append(new_d)

        return pass_dicts


    def _filter_dicts(self):
        '''Filters out all the report_dicts that do not pass the cutoffs. If any ref sequence
           loses all of its report_dicts, then it is completely removed.'''
        keys_to_remove = set()

        for ref_name in self.report:
            for ctg_name in self.report[ref_name]:
                self.report[ref_name][ctg_name] = self._filter_list_of_dicts(self.report[ref_name][ctg_name])
                if len(self.report[ref_name][ctg_name]) == 0:
                    keys_to_remove.add((ref_name, ctg_name))

        refs_to_remove = set()

        for ref_name, ctg_name in keys_to_remove:
            del self.report[ref_name][ctg_name]
            if len(self.report[ref_name]) == 0:
                refs_to_remove.add(ref_name)

        for ref_name in refs_to_remove:
            del self.report[ref_name]


    def _write_report_tsv(self, outfile):
        f = pyfastaq.utils.open_file_write(outfile)
        print('#' + '\t'.join(report.columns), file=f)

        for ref_name in sorted(self.report):
            for ctg_name, report_dicts in sorted(self.report[ref_name].items()):
                for d in report_dicts:
                    print(ReportFilter._dict_to_report_line(d), file=f)

        pyfastaq.utils.close(f)


    def _write_report_xls(self, outfile):
        workbook = openpyxl.Workbook()
        worksheet = workbook.worksheets[0]
        worksheet.title = 'ARIBA_report'
        worksheet.append(report.columns)

        for ref_name in sorted(self.report):
            for ctg_name, report_dicts in sorted(self.report[ref_name].items()):
                for d in report_dicts:
                    worksheet.append([str(d[x]) for x in report.columns])

        workbook.save(outfile)


    def run(self, outprefix):
        self._filter_dicts()
        self._write_report_xls(outprefix + '.xls')
        self._write_report_tsv(outprefix + '.tsv')

