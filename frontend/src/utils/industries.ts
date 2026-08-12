// 51job 行业字典（来源 https://js.51jobcdn.com/in/js/2023/dd/dd_industry.json）。
// 与 keyword.industry 字段对应：存叶子编码，逗号分隔。
export interface IndustryOption {
  value: string
  label: string
  children?: IndustryOption[]
}

export const INDUSTRY_TREE: IndustryOption[] = [
  {
    value: '01',
    label: '计算机/互联网/通信/电子',
    children: [
      { value: '01', label: '计算机软件' },
      { value: '37', label: '计算机硬件' },
      { value: '38', label: '计算机服务(系统、数据服务、维修)' },
      { value: '31', label: '通信/电信/网络设备' },
      { value: '39', label: '通信/电信运营、增值服务' },
      { value: '32', label: '互联网/电子商务' },
      { value: '40', label: '网络游戏' },
      { value: '02', label: '电子技术/半导体/集成电路' },
      { value: '35', label: '仪器仪表/工业自动化' },
    ],
  },
  {
    value: '41',
    label: '会计/金融/银行/保险',
    children: [
      { value: '41', label: '会计/审计' },
      { value: '03', label: '金融/投资/证券' },
      { value: '42', label: '银行' },
      { value: '43', label: '保险' },
      { value: '62', label: '信托/担保/拍卖/典当' },
    ],
  },
  {
    value: '04',
    label: '贸易/消费/制造/营运',
    children: [
      { value: '04', label: '贸易/进出口' },
      { value: '22', label: '批发/零售' },
      { value: '05', label: '快速消费品(食品、饮料、化妆品)' },
      { value: '06', label: '服装/纺织/皮革' },
      { value: '44', label: '家具/家电/玩具/礼品' },
      { value: '60', label: '奢侈品/收藏品/工艺品/珠宝' },
      { value: '45', label: '办公用品及设备' },
      { value: '14', label: '机械/设备/重工' },
      { value: '33', label: '汽车' },
      { value: '65', label: '汽车零配件' },
    ],
  },
  {
    value: '08',
    label: '制药/医疗',
    children: [
      { value: '08', label: '制药/生物工程' },
      { value: '46', label: '医疗/护理/卫生' },
      { value: '47', label: '医疗设备/器械' },
    ],
  },
  {
    value: '12',
    label: '广告/媒体',
    children: [
      { value: '12', label: '广告' },
      { value: '48', label: '公关/市场推广/会展' },
      { value: '49', label: '影视/媒体/艺术/文化传播' },
      { value: '13', label: '文字媒体/出版' },
      { value: '15', label: '印刷/包装/造纸' },
    ],
  },
  {
    value: '26',
    label: '房地产/建筑',
    children: [
      { value: '26', label: '房地产' },
      { value: '09', label: '建筑/建材/工程' },
      { value: '50', label: '家居/室内设计/装潢' },
      { value: '51', label: '物业管理/商业中心' },
      { value: '34', label: '中介服务' },
      { value: '63', label: '租赁服务' },
    ],
  },
  {
    value: '07',
    label: '专业服务/教育/培训',
    children: [
      { value: '07', label: '专业服务(咨询、人力资源、财会)' },
      { value: '59', label: '外包服务' },
      { value: '52', label: '检测，认证' },
      { value: '18', label: '法律' },
      { value: '23', label: '教育/培训/院校' },
      { value: '24', label: '学术/科研' },
    ],
  },
  {
    value: '11',
    label: '服务业',
    children: [
      { value: '11', label: '餐饮业' },
      { value: '53', label: '酒店/旅游' },
      { value: '17', label: '娱乐/休闲/体育' },
      { value: '54', label: '美容/保健' },
      { value: '27', label: '生活服务' },
    ],
  },
  {
    value: '21',
    label: '物流/运输',
    children: [
      { value: '21', label: '交通/运输/物流' },
      { value: '55', label: '航天/航空' },
    ],
  },
  {
    value: '19',
    label: '能源/环保/化工',
    children: [
      { value: '19', label: '石油/化工/矿产/地质' },
      { value: '16', label: '采掘业/冶炼' },
      { value: '36', label: '电气/电力/水利' },
      { value: '61', label: '新能源' },
      { value: '56', label: '原材料和加工' },
      { value: '20', label: '环保' },
    ],
  },
  {
    value: '28',
    label: '政府/非营利组织/其他',
    children: [
      { value: '28', label: '政府/公共事业' },
      { value: '57', label: '非营利组织' },
      { value: '29', label: '农/林/牧/渔' },
      { value: '58', label: '多元化业务集团公司' },
    ],
  },
]

const INDUSTRY_NAME_MAP: Record<string, string> = (() => {
  const m: Record<string, string> = {}
  const walk = (nodes: IndustryOption[]) => {
    for (const n of nodes) {
      m[n.value] = n.label
      if (n.children?.length) walk(n.children)
    }
  }
  walk(INDUSTRY_TREE)
  return m
})()

export function industryNames(codes: string | null | undefined): string {
  if (!codes) return '-'
  return codes
    .split(',')
    .map((c) => INDUSTRY_NAME_MAP[c.trim()] ?? c.trim())
    .join('、')
}
