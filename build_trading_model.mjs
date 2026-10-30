import fs from 'node:fs/promises';
import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const outDir = 'outputs';
await fs.mkdir(outDir, { recursive: true });
const wb = Workbook.create();
const dash = wb.worksheets.add('总览');
const regime = wb.worksheets.add('大盘阶段');
const pos = wb.worksheets.add('持仓管理');
const pool = wb.worksheets.add('股票池');
const log = wb.worksheets.add('交易日志');
const score = wb.worksheets.add('大盘评分');

const navy = '#17365D', blue = '#D9EAF7', light = '#F4F7FA', yellow = '#FFF2CC', red = '#FCE4D6', green = '#E2F0D9', gray = '#666666';
for (const s of [dash, regime, pos, pool, log, score]) { s.showGridLines = false; }

score.getRange('A1:F1').merge(); score.getRange('A1').values = [['大盘评分｜每天输入 0/1，辅助判断阶段']];
score.getRange('A3:F3').values = [['指标','输入值','判断标准','得分','备注','今日日期']];
score.getRange('A4:F9').values = [
 ['沪深300趋势',1,'站上20日线=1，否则=0',null,'2026-08-28收盘录入',new Date()],
 ['中证1000趋势',1,'站上20日线=1，否则=0',null,'2026-08-28收盘录入',new Date()],
 ['两市成交额',0,'高于近20日均值=1，否则=0',null,'2026-08-28收盘录入',new Date()],
 ['上涨/下跌家数',1,'上涨家数明显占优=1，否则=0',null,'2026-08-28收盘录入',new Date()],
 ['涨停/跌停结构',1,'涨停多、跌停少=1，否则=0',null,'2026-08-28收盘录入',new Date()],
 ['科技主线强弱',1,'科技板块强于大盘=1，否则=0',null,'半导体偏强，CPO内部有分化',new Date()],
];
for (let r=4;r<=9;r++) score.getRange(`D${r}`).formulas=[[`=B${r}`]];
score.getRange('A11:B16').values = [['评分结果','数值'],['总分',null],['建议阶段',null],['建议总仓位下限',null],['建议总仓位上限',null],['使用提示','评分是辅助工具，连续两天失效时下调一级']];
score.getRange('B12').formulas=[['=SUM(D4:D9)']];
score.getRange('B13').formulas=[['=IF(B12<=1,"系统风险",IF(B12=2,"弱势震荡",IF(B12<=4,"修复阶段","主升阶段")))']];
score.getRange('B14').formulas=[['=INDEX(\'大盘阶段\'!C4:C8,MATCH(B13,\'大盘阶段\'!A4:A8,0))']];
score.getRange('B15').formulas=[['=INDEX(\'大盘阶段\'!D4:D8,MATCH(B13,\'大盘阶段\'!A4:A8,0))']];
score.getRange('D11:F16').values=[['仓位换算','金额','说明'],['建议总仓位下限',null,'总资产×下限'],['建议总仓位上限',null,'总资产×上限'],['建议现金下限',null,'总资产×(1-上限)'],['进攻仓上限',null,'总资产×进攻上限'],[null,null,null]];
score.getRange('E12').formulas=[['=\'大盘阶段\'!B12*B14']]; score.getRange('E13').formulas=[['=\'大盘阶段\'!B12*B15']]; score.getRange('E14').formulas=[['=\'大盘阶段\'!B12*(1-B15)']]; score.getRange('E15').formulas=[['=\'大盘阶段\'!B12*INDEX(\'大盘阶段\'!E4:E8,MATCH(B13,\'大盘阶段\'!A4:A8,0))']];

// Regime sheet
regime.getRange('A1:F1').merge(); regime.getRange('A1').values = [['大盘阶段与总仓位规则']];
regime.getRange('A3:F3').values = [['阶段','典型特征','总仓位下限','总仓位上限','进攻仓上限','操作说明']];
regime.getRange('A4:F8').values = [
 ['系统风险','指数破位、普跌、成交额萎缩',0.2,0.3,0.1,'优先保现金，停止新增中线仓'],
 ['弱势震荡','止跌但主线不明',0.4,0.5,0.3,'轻仓试错，等待主线'],
 ['修复阶段','站回短期均线，赚钱效应恢复',0.6,0.7,0.5,'逐步增加核心仓'],
 ['主升阶段','指数、成交量、主线同步走强',0.8,0.95,0.65,'允许接近满仓，但保留调整空间'],
 ['高位分歧','冲高回落、热点轮动加快',0.55,0.7,0.45,'降低弹性仓，保留强趋势标的'],
];
regime.getRange('A10:B10').values = [['输入区','值']];
regime.getRange('A11:B14').values = [['当前阶段','修复阶段'],['总资产',1100000],['当前总仓位',0],['备注','阶段每周评估，出现连续失效信号时下调一级']];
regime.getRange('B11').dataValidation = {rule:{type:'list',values:['系统风险','弱势震荡','修复阶段','主升阶段','高位分歧']}};
regime.getRange('B13').formulas = [['=SUM(\'持仓管理\'!F7:F12)/B12']];
regime.getRange('D10:E10').values = [['自动输出','值']];
regime.getRange('D11:E14').values = [['建议总仓位下限',null],['建议总仓位上限',null],['建议进攻仓上限',null],['建议现金下限',null]];
regime.getRange('E11').formulas = [['=INDEX(C4:C8,MATCH(B11,A4:A8,0))']];
regime.getRange('E12').formulas = [['=INDEX(D4:D8,MATCH(B11,A4:A8,0))']];
regime.getRange('E13').formulas = [['=INDEX(E4:E8,MATCH(B11,A4:A8,0))']];
regime.getRange('E14').formulas = [['=1-E12']];

// Positions
pos.getRange('A1:N1').merge(); pos.getRange('A1').values = [['持仓管理｜只需填写蓝色输入格']];
pos.getRange('A3:B6').values = [['输入项','值'],['总资产',null],['当前阶段',null],['总仓位上限',null]];
pos.getRange('B4').formulas = [['=\'大盘阶段\'!B12']]; pos.getRange('B5').formulas = [['=\'大盘阶段\'!B11']]; pos.getRange('B6').formulas = [['=\'大盘阶段\'!E12']];
pos.getRange('A8:N8').values = [['位置','代码','名称','类型','方向','市值','实际占比','目标下限','目标上限','偏离','风险预算','止损幅度','潜在亏损','状态']];
pos.getRange('A9:A14').values = [['进攻1'],['进攻2'],['进攻3'],['进攻4'],['防守1'],['防守2']];
pos.getRange('D9:D14').values = [['中线'],['中线'],['中线'],['短线'],['中线'],['中线']];
pos.getRange('E9:E14').values = [['进攻'],['进攻'],['进攻'],['进攻'],['防守'],['防守']];
pos.getRange('H9:I14').values = [[0.15,0.25],[0.12,0.2],[0.08,0.15],[0.05,0.1],[0.1,0.15],[0.05,0.1]];
pos.getRange('K9:K14').values = [[11000],[11000],[11000],[11000],[11000],[11000]];
pos.getRange('L9:L14').values = [[0.1],[0.1],[0.12],[0.08],[0.15],[0.15]];
for (let r=9;r<=14;r++) {
 pos.getRange(`G${r}`).formulas = [[`=IFERROR(F${r}/$B$4,0)`]];
 pos.getRange(`J${r}`).formulas = [[`=G${r}-AVERAGE(H${r}:I${r})`]];
 pos.getRange(`M${r}`).formulas = [[`=F${r}*L${r}`]];
 pos.getRange(`N${r}`).formulas = [[`=IF(F${r}=0,"空缺",IF(G${r}>I${r},"超上限",IF(G${r}<H${r},"低于下限","正常")))`]];
}
pos.getRange('A16:F18').values = [['组合检查','当前值','阈值','状态','说明',null],['总仓位',null,null,null,'超过当前阶段上限时先停止加仓',null],['进攻仓',null,null,null,'进攻仓包含中线科技与短线仓',null]];
pos.getRange('B17').formulas = [['=SUM(F9:F14)/$B$4']]; pos.getRange('C17').formulas = [['=$B$6']]; pos.getRange('D17').formulas = [['=IF(B17>C17,"超限","正常")']];
pos.getRange('B18').formulas = [['=SUMIF(E9:E14,"进攻",F9:F14)/$B$4']]; pos.getRange('C18').formulas = [['=INDEX(\'大盘阶段\'!E4:E8,MATCH($B$5,\'大盘阶段\'!A4:A8,0))']]; pos.getRange('D18').formulas = [['=IF(B18>C18,"超限","正常")']];

// Dashboard
dash.getRange('A1:H1').merge(); dash.getRange('A1').values = [['个人交易模型｜总览']];
dash.getRange('A3:B9').values = [['核心指标','当前值'],['总资产',null],['市场阶段',null],['总仓位',null],['现金比例',null],['进攻仓比例',null],['组合状态',null]];
dash.getRange('B4').formulas = [['=\'大盘阶段\'!B12']]; dash.getRange('B5').formulas = [['=\'大盘阶段\'!B11']]; dash.getRange('B6').formulas = [['=\'持仓管理\'!B17']]; dash.getRange('B7').formulas = [['=1-B6']]; dash.getRange('B8').formulas = [['=\'持仓管理\'!B18']]; dash.getRange('B9').formulas = [['=IF(\'持仓管理\'!D17="超限","总仓位超限",IF(\'持仓管理\'!D18="超限","进攻仓超限","正常"))']];
dash.getRange('D3:H3').values = [['使用顺序','1. 先在“大盘阶段”选择市场阶段','2. 在“持仓管理”填写蓝色输入格','3. 看状态与超限提示','4. 交易后登记“交易日志”']];
dash.getRange('A12:G17').values = [['六个持仓位','定位','建议上限','当前市值','实际比例','状态',null],['进攻1','最熟悉的科技核心','25%',null,null,null,null],['进攻2','第二科技主线','20%',null,null,null,null],['进攻3','产业链补充','15%',null,null,null,null],['进攻4','短线/轮动','10%',null,null,null,null],['防守1-2','有色/低相关方向','25%',null,null,null,null]];
for (let i=0;i<6;i++){const rr=13+i; const pr=9+i; dash.getRange(`D${rr}`).formulas=[[`=\'持仓管理\'!F${pr}`]]; dash.getRange(`E${rr}`).formulas=[[`=\'持仓管理\'!G${pr}`]]; dash.getRange(`F${rr}`).formulas=[[`=\'持仓管理\'!N${pr}`]];}

// Pool
pool.getRange('A1:H1').merge(); pool.getRange('A1').values = [['股票池｜研究池与交易池分层']];
pool.getRange('A3:H3').values = [['代码','名称','题材/产业链','池级别','交易类型','熟悉度','核心逻辑','失效条件']];
pool.getRange('A4:H12').values = [
 ['300308','中际旭创','CPO/光模块','熟悉交易池','中线/短线','深度熟悉','',''],["'000988",'华工科技','光通信/电子','熟悉交易池','中线/短线','较熟悉','',''],['688498','源杰科技','光芯片/CPO','观察池','短线','短期交易','',''],['300394','天孚通信','光器件/CPO','观察池','中线/短线','短期交易','',''],['688008','澜起科技','内存接口/半导体','核心研究池','中线','较熟悉','',''],['601138','工业富联','AI服务器/电子制造','核心研究池','中线','较熟悉','',''],['600711','盛屯矿业','有色/能源金属','防守研究池','中线','熟悉股性','',''],['688825','长鑫科技','存储/新股','独立统计','观察','新股','',''],["'002235",'安妮股份','非核心题材','观察池','短线','试水','','']
];

// Trade log
log.getRange('A1:L1').merge(); log.getRange('A1').values = [['交易日志｜每次交易都留下可复盘证据']];
log.getRange('A3:L3').values = [['日期','代码','名称','中线/短线','题材','买入理由','验证指标','失效条件','计划仓位','买入价','卖出价','结果/复盘']];
log.getRange('A4:L23').format.rowHeight = 30;

// Styles
const headers=[score.getRange('A3:F3'),score.getRange('A11:B11'),score.getRange('D11:F11'),regime.getRange('A3:F3'),regime.getRange('A10:B10'),regime.getRange('D10:E10'),pos.getRange('A8:N8'),pos.getRange('A16:F16'),dash.getRange('A3:B3'),dash.getRange('A12:H12'),pool.getRange('A3:H3'),log.getRange('A3:L3')];
for (const h of headers){h.format={fill:navy,font:{bold:true,color:'#FFFFFF'},horizontalAlignment:'center',verticalAlignment:'center'};h.format.rowHeight=24;}
for (const s of [dash,regime,pos,pool,log,score]) { s.getUsedRange().format.font={name:'Aptos',size:10}; }
for (const title of [dash.getRange('A1:H1'),regime.getRange('A1:F1'),pos.getRange('A1:N1'),pool.getRange('A1:H1'),log.getRange('A1:L1')]) { title.format={fill:navy,font:{bold:true,color:'#FFFFFF',size:16},horizontalAlignment:'left',verticalAlignment:'center'}; title.format.rowHeight=30; }
for (const input of [regime.getRange('B11:B12'),pos.getRange('B9:F14'),pool.getRange('A4:H50'),log.getRange('A4:L23')]) input.format.font={color:'#0000FF'};
pos.getRange('B9:F14').format.fill=yellow; regime.getRange('B11:B12').format.fill=yellow;
score.getRange('B4:B9').format={fill:yellow,font:{color:'#0000FF'}}; score.getRange('B4:B9').dataValidation={rule:{type:'list',values:[0,1]}};
for (const s of [dash,regime,pos,pool,log]) { const u=s.getUsedRange(); u.format.verticalAlignment='center'; }
regime.getRange('C4:E8').format.numberFormat='0%'; regime.getRange('B12').format.numberFormat='#,##0'; regime.getRange('B13:E14').format.numberFormat='0.0%';
pos.getRange('B4').format.numberFormat='#,##0'; pos.getRange('F9:F14').format.numberFormat='#,##0'; pos.getRange('G9:J14').format.numberFormat='0.0%'; pos.getRange('K9:M14').format.numberFormat='#,##0'; pos.getRange('L9:L14').format.numberFormat='0.0%'; pos.getRange('B17:C18').format.numberFormat='0.0%';
dash.getRange('B4').format.numberFormat='#,##0'; dash.getRange('B6:B8').format.numberFormat='0.0%'; dash.getRange('E13:E17').format.numberFormat='0.0%';
score.getRange('B14:B15').format.numberFormat='0.0%'; score.getRange('E12:E15').format.numberFormat='#,##0'; score.getRange('F4:F9').format.numberFormat='yyyy-mm-dd';
for (const r of [pos.getRange('N9:N14'),pos.getRange('D17:D18'),dash.getRange('B9'),dash.getRange('F13:F17')]) { r.conditionalFormats.add('containsText',{text:'超',format:{fill:'#F4CCCC',font:{color:'#9C0006',bold:true}}}); }
for (const s of [dash,regime,pos,pool,log,score]) { s.freezePanes.freezeRows(3); }
dash.getRange('A3:H17').format.borders={preset:'inside',style:'thin',color:'#D9E2F3'}; pos.getRange('A8:N18').format.borders={preset:'inside',style:'thin',color:'#D9E2F3'}; pool.getRange('A3:H12').format.borders={preset:'inside',style:'thin',color:'#D9E2F3'}; log.getRange('A3:L23').format.borders={preset:'inside',style:'thin',color:'#D9E2F3'};
for (const [s, widths] of [[dash,[18,18,18,18,14,16,12,12]],[regime,[16,30,14,14,14,34]],[pos,[12,12,16,12,10,14,12,12,12,12,12,12,14,14]],[pool,[12,16,20,16,14,14,28,28]],[log,[12,12,16,12,16,30,24,28,12,12,12,36]],[score,[18,12,30,10,28,14]]]) { widths.forEach((w,i)=>s.getRangeByIndexes(0,i,1,1).format.columnWidth=w); }

const err = await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A',options:{useRegex:true,maxResults:100}});
if (err.ndjson && !err.ndjson.includes('matched 0 entries')) throw new Error(err.ndjson);
const check = await wb.inspect({kind:'table',range:'总览!A3:H17',include:'values,formulas',tableMaxRows:20,tableMaxCols:10});
console.log(check.ndjson);
const preview = await wb.render({sheetName:'总览',range:'A1:H17',scale:1.5,format:'png'});
await fs.writeFile(`${outDir}/交易框架_总览.png`, new Uint8Array(await preview.arrayBuffer()));
for (const [name, range] of [['大盘阶段','A1:F14'],['持仓管理','A1:N18'],['股票池','A1:H12'],['交易日志','A1:L12'],['大盘评分','A1:F16']]) {
  const p = await wb.render({sheetName:name,range,scale:1.2,format:'png'});
  await fs.writeFile(`${outDir}/交易框架_${name}.png`, new Uint8Array(await p.arrayBuffer()));
}
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(`${outDir}/个人交易框架_仓位管理_2026-08-28收盘.xlsx`);
