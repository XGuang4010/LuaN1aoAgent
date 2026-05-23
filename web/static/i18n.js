// 国际化配置
const i18n = {
  zh: {
    // Topbar
    'brand': '鸾鸟Agent',
    'view.exec': '攻击图',
    'view.causal': '因果图',
    'input.goal': '输入目标...',
    'input.taskid': '任务ID',
    'btn.create': '新建',
    'btn.mcp': 'MCP',
    'btn.inject': '注入',
    'btn.refresh': '刷新',
    'btn.stop': '终止',
    'btn.track_title': '追踪活跃节点',

    // Sidebar
    // Dashboard Filters
    'filter.all': '全部',
    'filter.running': '运行中',
    'filter.completed': '已完成',
    'filter.crashed': '崩溃',
    'sidebar.operations': '任务管理台',

    // Right Panel
    'panel.details': '节点详情',
    'panel.notselected': '未选择节点',
    'panel.type': '类型',
    'panel.status': '状态',
    'panel.description': '描述',
    'panel.thought': '思考',
    'panel.goal': '目标',
    'panel.tool': '工具',
    'panel.args': '参数',
    'panel.result': '结果',
    'panel.observation': '观察',
    'panel.params': '参数',
    'panel.target': '目标',
    'panel.no_overview': '暂无概览信息',
    'panel.no_findings': '暂无发现数据',
    'panel.no_evidence': '暂无证据关联',
    'panel.no_raw': '暂无原始输出',
    'panel.evidence_count': '关联证据',
    'panel.view': '查看',
    'panel.confidence_label': '置信度',
    'panel.no_hypothesis': '未命名假设',

    // Modals
    'modal.mcp.title': 'MCP服务配置',
    'modal.mcp.name': '服务名',
    'modal.mcp.command': '启动命令',
    'modal.mcp.args': '参数 (JSON)',
    'modal.mcp.env': '环境变量 (JSON)',
    'modal.inject.title': '注入任务',
    'modal.inject.opid': 'Operation ID',
    'modal.inject.subtask': '子任务 (JSON)',
    'btn.submit': '提交',
    'btn.cancel': '取消',

    // Status
    'status.completed': '已完成',
    'status.failed': '失败',
    'status.in_progress': '进行中',
    'status.pending': '待执行',
    'status.deprecated': '已废弃',
    'status.running': '运行中',
    'status.mission_accomplished': '全局任务目标达成！',
    'status.aborted': '已终止',

    // Node Types
    'type.root': '主任务',
    'type.task': '子任务',
    'type.action': '执行步骤',

    // Tabs
    'tab.overview': '概览',
    'tab.findings': '发现',
    'tab.evidence': '证据',
    'tab.raw': '原始输出',
    'tab.suggestions': '建议',
    'tab.hypothesis': '假设',

    // Timeline
    'timeline.no_data': '暂无数据',
    'timeline.planning': '正在规划中...',
    'timeline.completed': '已完成',
    'timeline.findings': '发现',

    // Causal Graph
    'causal.keyfact': '关键事实',
    'causal.evidence': '证据',
    'causal.hypothesis': '假设',
    'causal.vulnerability': '漏洞',
    'causal.confirmed_vuln': '已确认漏洞',
    'causal.flag': 'Flag',

    // Legend
    'legend.title': '图例',
    'legend.node_types': '节点类型',
    'legend.node_status': '节点状态',

    // Suggestions
    'suggestion.header': '基于当前发现，建议下一步：',
    'suggestion.no_data': '暂无足够数据生成建议',
    'suggestion.plan': '重新规划任务...',
    'suggestion.new_target': '添加新的测试目标...',
    'suggestion.exploit': '尝试利用已发现的漏洞...',
    'suggestion.manual': '执行手动验证步骤...',
    'suggestion.fallback_1': '根据发现信息进行深入分析',
    'suggestion.fallback_2': '搜索相关已知漏洞',
    'suggestion.fallback_3': '尝试扩大攻击面',
    'suggestion.open_port_1': '对开放端口进行 banner 抓取',
    'suggestion.open_port_2': '使用 nmap 进行服务版本探测',
    'suggestion.open_port_3': '检查常见弱口令服务',
    'suggestion.service_1': '根据服务版本搜索已知漏洞 (searchsploit)',
    'suggestion.service_2': '尝试使用该服务的默认凭据',
    'suggestion.service_3': '测试服务配置安全性',
    'suggestion.subdomain_1': '对发现的子域名进行 HTTP 探测',
    'suggestion.subdomain_2': '对子域名进行端口扫描',
    'suggestion.subdomain_3': '收集子域名的 DNS 记录',
    'suggestion.vuln_1': '确认漏洞是否真实可被利用',
    'suggestion.vuln_2': '尝试搜索公开的漏洞利用代码',
    'suggestion.vuln_3': '分析漏洞影响范围',
    'suggestion.url_1': '对 URL 进行目录扫描 (dirsearch)',
    'suggestion.url_2': '测试常见 Web 漏洞 (SQLi/XSS/SSRF)',
    'suggestion.url_3': '分析页面 JavaScript 和 API 端点',
    'suggestion.http_header_1': '检查安全头缺失导致的潜在风险',
    'suggestion.http_header_2': '分析 CORS 配置安全性',
    'suggestion.http_header_3': '检查 Cookie 安全属性设置',
    'suggestion.technology_1': '根据技术栈搜索已知漏洞',
    'suggestion.technology_2': '检查组件版本是否过时',
    'suggestion.technology_3': '寻找版本相关的 CVE',
    'suggestion.cms_1': '尝试 CMS 指纹识别',
    'suggestion.cms_2': '检查 CMS 版本漏洞',
    'suggestion.cms_3': '寻找 CMS 后台路径',
    'suggestion.email_1': '验证邮箱有效性',
    'suggestion.email_2': '检查邮件服务器配置',
    'suggestion.email_3': '测试邮件注入或 SPF 记录',
    'suggestion.dns_1': '检查域名的 DNS 记录',
    'suggestion.dns_2': '测试区域传输漏洞',
    'suggestion.dns_3': '寻找子域名劫持机会',

    // Messages
    'msg.no_opid': '请先选择一个 Operation',
    'msg.confirm_abort': '确认要终止当前操作吗？',
    'msg.task_created': '任务创建成功',
    'msg.task_injected': '任务注入成功',
    'msg.operation_aborted': '操作已终止',
    'msg.click_to_load': '点击标签加载假设数据',
    'msg.loading': '加载中...',
    'msg.load_failed': '加载失败',
    'msg.no_hypotheses': '暂无假设数据',

    // Hypothesis Panel
    'panel.hypothesis_count': '共',
    'panel.hypothesis_sorted': '条假设 (按置信度排序)',
    'panel.confidence': '置信度',

    // Phase Status
    'phase.reflecting': '🤔 反思中...',
    'phase.planning': '📋 规划中...',
    'phase.executing': '⚡ 执行中...',

    // MCP Modal
    'mcp.title': '管理 MCP 服务器',
    'mcp.current': '当前服务器',
    'mcp.loading': '加载中...',
    'mcp.add_new': '添加新服务器',
    'mcp.name': '名称',
    'mcp.command': '命令',
    'mcp.args': '参数（逗号分隔）',
    'mcp.env': '环境变量（JSON）',
    'mcp.add_reload': '添加并重载',
    'mcp.no_servers': '未配置服务器',
    'mcp.required': '名称和命令为必填项',
    'mcp.invalid_json': '环境变量 JSON 格式无效',
    'mcp.success': '服务器已添加并重载！',
    'mcp.error': '错误',

    // Create Task Modal
    'modal.create.title': '新建任务',
    'modal.create.goal': '任务目标 *',
    'modal.create.taskname': '任务名称',
    'modal.create.hitl': '人机协同模式',
    'modal.create.hitl_on': '开启',
    'modal.create.hitl_off': '关闭',
    'modal.create.hitl_desc': '开启后Agent的关键决策需经您批准',
    'modal.create.output_mode': '输出模式',
    'modal.create.advanced': '高级配置',
    'modal.create.llm_hint': '自定义各角色的LLM模型（留空使用默认配置）',
    'btn.cancel': '取消',
    'btn.close': '关闭',
    'btn.create_start': '启动任务',
  },

  en: {
    // Topbar
    'brand': 'LuanNiao Agent',
    'view.exec': 'Attack Graph',
    'view.causal': 'Causal Graph',
    'input.goal': 'Enter goal...',
    'input.taskid': 'Task ID',
    'btn.create': 'Create',
    'btn.mcp': 'MCP',
    'btn.inject': 'Inject',
    'btn.refresh': 'Refresh',
    'btn.stop': 'Stop',
    'btn.track_title': 'Track active node',

    // Sidebar
    // Dashboard Filters
    'filter.all': 'All',
    'filter.running': 'Running',
    'filter.completed': 'Completed',
    'filter.crashed': 'Crashed',
    'sidebar.operations': 'Task Dashboard',

    // Right Panel
    'panel.details': 'Node Details',
    'panel.notselected': 'No node selected',
    'panel.type': 'Type',
    'panel.status': 'Status',
    'panel.description': 'Description',
    'panel.thought': 'Thought',
    'panel.goal': 'Goal',
    'panel.tool': 'Tool',
    'panel.args': 'Arguments',
    'panel.result': 'Result',
    'panel.observation': 'Observation',
    'panel.params': 'Params',
    'panel.target': 'Target',
    'panel.no_overview': 'No overview information',
    'panel.no_findings': 'No findings data',
    'panel.no_evidence': 'No evidence linked',
    'panel.no_raw': 'No raw output',
    'panel.evidence_count': 'Linked Evidence',
    'panel.view': 'View',
    'panel.confidence_label': 'Confidence',
    'panel.no_hypothesis': 'Unnamed Hypothesis',

    // Modals
    'modal.mcp.title': 'MCP Service Config',
    'modal.mcp.name': 'Service Name',
    'modal.mcp.command': 'Command',
    'modal.mcp.args': 'Args (JSON)',
    'modal.mcp.env': 'Environment (JSON)',
    'modal.inject.title': 'Inject Task',
    'modal.inject.opid': 'Operation ID',
    'modal.inject.subtask': 'Subtask (JSON)',
    'btn.submit': 'Submit',
    'btn.cancel': 'Cancel',

    // Status
    'status.completed': 'Completed',
    'status.failed': 'Failed',
    'status.in_progress': 'In Progress',
    'status.pending': 'Pending',
    'status.deprecated': 'Deprecated',
    'status.running': 'Running',
    'status.mission_accomplished': 'Global Mission Accomplished!',
    'status.aborted': 'Aborted',

    // Node Types
    'type.root': 'Root Task',
    'type.task': 'Subtask',
    'type.action': 'Action',

    // Tabs
    'tab.overview': 'Overview',
    'tab.findings': 'Findings',
    'tab.evidence': 'Evidence',
    'tab.raw': 'Raw Output',
    'tab.suggestions': 'Suggestions',
    'tab.hypothesis': 'Hypothesis',

    // Timeline
    'timeline.no_data': 'No data',
    'timeline.planning': 'Planning...',
    'timeline.completed': 'Completed',
    'timeline.findings': 'findings',

    // Causal Graph
    'causal.keyfact': 'Key Fact',
    'causal.evidence': 'Evidence',
    'causal.hypothesis': 'Hypothesis',
    'causal.vulnerability': 'Vulnerability',
    'causal.confirmed_vuln': 'Confirmed Vulnerability',
    'causal.flag': 'Flag',

    // Legend
    'legend.title': 'Legend',
    'legend.node_types': 'Node Types',
    'legend.node_status': 'Node Status',

    // Suggestions
    'suggestion.header': 'Based on current findings, suggested next steps:',
    'suggestion.no_data': 'Not enough data to generate suggestions',
    'suggestion.plan': 'Re-plan tasks...',
    'suggestion.new_target': 'Add new test target...',
    'suggestion.exploit': 'Try exploiting discovered vulnerabilities...',
    'suggestion.manual': 'Execute manual verification steps...',
    'suggestion.fallback_1': 'Perform in-depth analysis based on findings',
    'suggestion.fallback_2': 'Search for related known vulnerabilities',
    'suggestion.fallback_3': 'Try to expand the attack surface',
    'suggestion.open_port_1': 'Grab banner from open ports',
    'suggestion.open_port_2': 'Use nmap for service version detection',
    'suggestion.open_port_3': 'Check common weak password services',
    'suggestion.service_1': 'Search for known vulnerabilities by service version (searchsploit)',
    'suggestion.service_2': 'Try default credentials for this service',
    'suggestion.service_3': 'Test service configuration security',
    'suggestion.subdomain_1': 'Perform HTTP probing on discovered subdomains',
    'suggestion.subdomain_2': 'Perform port scanning on subdomains',
    'suggestion.subdomain_3': 'Collect DNS records for subdomains',
    'suggestion.vuln_1': 'Confirm whether the vulnerability is truly exploitable',
    'suggestion.vuln_2': 'Try searching for public exploit code',
    'suggestion.vuln_3': 'Analyze the scope of vulnerability impact',
    'suggestion.url_1': 'Perform directory scanning on URL (dirsearch)',
    'suggestion.url_2': 'Test common web vulnerabilities (SQLi/XSS/SSRF)',
    'suggestion.url_3': 'Analyze page JavaScript and API endpoints',
    'suggestion.http_header_1': 'Check for potential risks from missing security headers',
    'suggestion.http_header_2': 'Analyze CORS configuration security',
    'suggestion.http_header_3': 'Check Cookie security attribute settings',
    'suggestion.technology_1': 'Search for known vulnerabilities based on technology stack',
    'suggestion.technology_2': 'Check if component versions are outdated',
    'suggestion.technology_3': 'Look for version-related CVEs',
    'suggestion.cms_1': 'Try CMS fingerprinting',
    'suggestion.cms_2': 'Check for CMS version vulnerabilities',
    'suggestion.cms_3': 'Look for CMS admin paths',
    'suggestion.email_1': 'Verify email validity',
    'suggestion.email_2': 'Check mail server configuration',
    'suggestion.email_3': 'Test for email injection or SPF records',
    'suggestion.dns_1': 'Check domain DNS records',
    'suggestion.dns_2': 'Test for zone transfer vulnerabilities',
    'suggestion.dns_3': 'Look for subdomain hijacking opportunities',

    // Messages
    'msg.no_opid': 'Please select an operation first',
    'msg.confirm_abort': 'Are you sure to abort current operation?',
    'msg.task_created': 'Task created successfully',
    'msg.task_injected': 'Task injected successfully',
    'msg.operation_aborted': 'Operation aborted',
    'msg.click_to_load': 'Click tab to load hypotheses',
    'msg.loading': 'Loading...',
    'msg.load_failed': 'Failed to load',
    'msg.no_hypotheses': 'No hypothesis data',

    // Hypothesis Panel
    'panel.hypothesis_count': '',
    'panel.hypothesis_sorted': ' hypotheses (sorted by confidence)',
    'panel.confidence': 'Confidence',

    // Phase Status
    'phase.reflecting': '🤔 Reflecting...',
    'phase.planning': '📋 Planning...',
    'phase.executing': '⚡ Executing...',

    // MCP Modal
    'mcp.title': 'Manage MCP Servers',
    'mcp.current': 'Current Servers',
    'mcp.loading': 'Loading...',
    'mcp.add_new': 'Add New Server',
    'mcp.name': 'Name',
    'mcp.command': 'Command',
    'mcp.args': 'Args (comma separated)',
    'mcp.env': 'Env (JSON)',
    'mcp.add_reload': 'Add & Reload',
    'mcp.no_servers': 'No servers configured.',
    'mcp.required': 'Name and command required',
    'mcp.invalid_json': 'Invalid JSON for Env',
    'mcp.success': 'Server added & reloaded!',
    'mcp.error': 'Error',

    // Create Task Modal
    'modal.create.title': 'Create Task',
    'modal.create.goal': 'Task Goal *',
    'modal.create.taskname': 'Task Name',
    'modal.create.hitl': 'Human-in-the-Loop',
    'modal.create.hitl_on': 'On',
    'modal.create.hitl_off': 'Off',
    'modal.create.hitl_desc': 'Agent\'s key decisions require your approval',
    'modal.create.output_mode': 'Output Mode',
    'modal.create.advanced': 'Advanced Configuration',
    'modal.create.llm_hint': 'Customize LLM models for each role (leave empty for defaults)',
    'btn.cancel': 'Cancel',
    'btn.close': 'Close',
    'btn.create_start': 'Start Task',
  }
};

// 当前语言，默认中文
let currentLang = localStorage.getItem('lang') || 'zh';

// 翻译函数
function t(key, defaultValue) {
  return i18n[currentLang][key] || defaultValue || key;
}

// 切换语言
function switchLanguage(lang) {
  if (!i18n[lang]) return;
  currentLang = lang;
  localStorage.setItem('lang', lang);
  updateUITexts();
  // 重新渲染图表以更新节点文本
  render(true);
}

// 更新UI中的文本
function updateUITexts() {
  // 更新所有带 data-i18n 属性的元素
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const translation = t(key);

    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      el.placeholder = translation;
    } else {
      el.textContent = translation;
    }
  });

  // 更新所有带 data-i18n-title 属性的元素
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    const key = el.getAttribute('data-i18n-title');
    el.title = t(key);
  });
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', () => {
  updateUITexts();
});
