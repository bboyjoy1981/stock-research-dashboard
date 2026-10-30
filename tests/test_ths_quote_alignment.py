from src.importers import read_tabular_upload


def test_double_tab_quote_export_keeps_column_alignment():
    header = ['.', '代码', '名称', '.', '涨幅', '现价', '涨跌', '买价', '卖价', '总手', '总金额', '现手', '换手', '委比%', '细分行业', '所属行业', '昨收', '开盘', '最高', '最低']
    row = '260.00\t\tSH600000\t浦发银行\t\t\t+3.27%\t\t9.48\t\t+0.30\t\t9.47\t\t9.48\t\t147484820\t1386209900\t13600↑\t\t0.443\t\t-83.24\t\t股份制银行\t银行\t\t9.18\t\t9.22\t\t9.49\t\t9.16'
    raw = ('\t\t'.join(header) + '\n' + row).encode('gb18030')
    item = read_tabular_upload(raw, 'Table.txt').iloc[0]
    assert item['成交额'] == 1386209900
    assert item['换手率'] == 0.443
    assert item['行业'] == '银行'
    assert float(item['昨收']) == 9.18
    assert float(item['最低']) == 9.16
