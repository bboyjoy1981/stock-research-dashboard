def test_index_parser_uses_provider_date_and_prices():
    from src.index_snapshot import parse_index_quotes
    fields = ['0'] * 38
    fields[1:6] = ['上证指数', '000001', '3842.19', '3830.45', '3839.25']
    fields[30:35] = ['20260930161500', '11.74', '0.31', '3851.22', '3833.09']
    result = parse_index_quotes('v_sh000001="' + '~'.join(fields) + '";')
    assert result.iloc[0]['交易日期'] == '2026-09-30'
    assert result.iloc[0]['价格'] == 3842.19
