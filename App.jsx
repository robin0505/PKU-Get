import React from 'react';
import { Phone, Mail, MessageCircle, MapPin, Printer, Trophy, BookOpen, Cpu, FlaskConical, Swords } from 'lucide-react';

const SectionTitle = ({ icon: Icon, children }) => (
  <h2 className="flex items-center gap-1.5 text-[12.5px] font-bold text-slate-800 uppercase tracking-[0.18em] mb-1.5">
    <span className="flex items-center justify-center w-4 h-4 text-indigo-600">
      <Icon size={13} strokeWidth={2.5} />
    </span>
    {children}
    <span className="flex-1 ml-1 h-px bg-gradient-to-r from-indigo-200 to-transparent"></span>
  </h2>
);

const Tag = ({ children, variant = 'default' }) => {
  const styles = {
    default: 'bg-slate-100 text-slate-700 border border-slate-200',
    accent: 'bg-indigo-50 text-indigo-700 border border-indigo-200',
    success: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
  };
  return (
    <span className={`inline-block text-[11px] px-2 py-0.5 rounded font-medium ${styles[variant]}`}>
      {children}
    </span>
  );
};

export default function App() {
  const handlePrint = () => window.print();

  return (
    <div className="min-h-screen bg-slate-200 py-10 print:py-0 print:bg-white font-sans text-gray-800">
      {/* 打印按钮 */}
      <button
        onClick={handlePrint}
        className="fixed top-8 right-8 bg-indigo-600 hover:bg-indigo-700 text-white p-3 rounded-full shadow-xl transition-all print:hidden flex items-center justify-center gap-2 group z-50"
        title="打印或导出 PDF"
      >
        <Printer size={18} />
        <span className="max-w-0 overflow-hidden whitespace-nowrap group-hover:max-w-xs group-hover:px-2 transition-all duration-300 ease-in-out text-sm">
          打印 / 导出 PDF
        </span>
      </button>

      <div className="max-w-[820px] mx-auto bg-white shadow-2xl print:shadow-none print:max-w-full box-border leading-relaxed rounded-sm overflow-hidden">

        {/* ── 头部 ── */}
        <header className="bg-gradient-to-br from-slate-800 to-slate-900 text-white px-10 py-5 print:px-10 print:py-4">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 mb-2">
            <h1 className="text-[1.75rem] font-extrabold tracking-[0.2em] text-white">潘子轩</h1>
            <p className="text-indigo-300 text-[12px] font-medium tracking-widest">
              应用物理学本科 · 北京大学 · GPU 系统与数据加速方向
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[12px] text-slate-300">
            <span className="flex items-center gap-1">
              <Phone size={12} className="text-indigo-400" />
              (+86) 15611009139
            </span>
            <span className="flex items-center gap-1">
              <Mail size={12} className="text-indigo-400" />
              2300012747@stu.pku.edu.cn
            </span>
            <span className="flex items-center gap-1">
              <MessageCircle size={12} className="text-indigo-400" />
              微信：_P_Z_X_
            </span>
            <span className="flex items-center gap-1">
              <MapPin size={12} className="text-indigo-400" />
              北京
            </span>
          </div>
        </header>

        <div className="px-10 py-5 print:px-10 print:py-4 space-y-3.5">

          {/* ── 教育经历 ── */}
          <section>
            <SectionTitle icon={BookOpen}>教育经历</SectionTitle>
            <div className="pl-1">
              <div className="flex justify-between items-baseline mb-0.5">
                <h3 className="text-[13.5px] font-bold text-slate-900">北京大学</h3>
                <span className="text-[11px] font-medium text-slate-500 tabular-nums">2023.09 – 2027.06</span>
              </div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-[12.5px] text-slate-600">应用物理学，本科</span>
                <Tag variant="accent">GPA：3.79 / 4.00</Tag>
              </div>
              <ul className="list-disc list-outside ml-4 text-[12px] text-slate-600 space-y-0.5 leading-snug">
                <li>
                  <strong className="text-slate-700">相关课程：</strong>
                  数据结构与算法（100）、计算机组织与体系结构（92.5）、深度学习中的高效计算方法（98）、芯片设计自动化与智能优化（98）、图神经网络（A）、电子信息学中的机器学习（90）
                </li>
                <li><strong className="text-slate-700">英语能力：</strong>CET-6 556</li>
              </ul>
            </div>
          </section>

          {/* ── 技术技能 ── */}
          <section>
            <SectionTitle icon={Cpu}>技术技能</SectionTitle>
            <div className="pl-1 grid grid-cols-1 gap-y-1 text-[12px]">
              {[
                { label: '编程语言', items: ['C++', 'Python', 'CUDA', 'PyTorch'] },
                { label: '系统与工具', items: ['Linux', 'Git', 'Docker', 'CMake', 'pybind11'] },
                { label: '性能与并行', items: ['CUDA 并行编程', 'OpenMP', 'Nsight Systems', 'CPU-GPU 异构调度'] },
                { label: '关注方向', items: ['GPU 数据加速', '异构计算', '性能分析与调优', 'AI 训练/推理 IO 优化', '分布式存缓系统'] },
              ].map(({ label, items }) => (
                <div key={label} className="flex items-start gap-2">
                  <span className="shrink-0 w-24 text-slate-500 font-medium pt-0.5">{label}</span>
                  <div className="flex flex-wrap gap-1">
                    {items.map(item => <Tag key={item}>{item}</Tag>)}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* ── 论文成果 ── */}
          <section>
            <SectionTitle icon={FlaskConical}>论文成果</SectionTitle>
            <div className="pl-3 border-l-2 border-indigo-300 py-0.5">
              <p className="text-[12.5px] font-semibold text-slate-800 italic leading-snug">
                Disentangled Differentiable Timing-Power Co-Optimization with Quad-Gradient Gate Sizing
              </p>
              <p className="mt-1 text-[12px] text-slate-600">
                <Tag variant="success">DAC 2026</Tag>
                <span className="ml-2">第一作者 · EDA 领域 CCF-A 类顶级会议</span>
              </p>
            </div>
          </section>

          {/* ── 科研 / 项目经历 ── */}
          <section>
            <SectionTitle icon={FlaskConical}>科研 / 项目经历</SectionTitle>
            <div className="space-y-3 pl-1">

              {/* 项目一：DiffOPT —— 按照腾讯 TEG AI 数据加速 JD 改写 */}
              <div className="relative pl-3 border-l-2 border-indigo-200 hover:border-indigo-400 transition-colors">
                <div className="flex justify-between items-start gap-3 mb-0.5">
                  <h3 className="text-[12.5px] font-bold text-slate-900 flex items-center flex-wrap gap-1.5">
                    大规模数据密集型 GPU 加速优化系统
                    <Tag variant="accent">DAC 2026 录用 · 一作</Tag>
                  </h3>
                  <span className="text-[11px] font-medium text-slate-500 shrink-0 tabular-nums">2025.01 – 2026.03</span>
                </div>
                <div className="text-[11px] font-medium text-indigo-500 mb-1">C++ / CUDA / Python / PyTorch · 林亦波课题组</div>
                <ul className="list-disc list-outside ml-4 text-[12px] text-slate-600 space-y-0.5 leading-snug">
                  <li>
                    开发和优化面向大规模图优化场景的 GPU 加速系统（40+ 自定义 PyTorch 算子，C++/CUDA 内核通过 pybind11 暴露），
                    管理百万节点 &times; 百万边的<strong className="text-slate-700">异构数据管线</strong>，
                    在 GPU 显存中统一编排位置、尺寸、时序等多维张量的<strong className="text-slate-700">存储布局与生命周期</strong>。
                  </li>
                  <li>
                    针对 LUT 查表的<strong className="text-slate-700">随机访问瓶颈</strong>，设计基于偏移索引的紧凑编码方案，
                    将异构类型的查找表统一编码为连续张量，减少不规则 GPU 内存访问；
                    通过 <code className="text-[11px] bg-slate-100 px-1 rounded">index_add_</code> scatter-reduce
                    将千万级数据点的梯度贡献高效归约到数百万节点。
                  </li>
                  <li>
                    构建<strong className="text-slate-700">多模式数值校准框架</strong>与完整的性能分析工具链，支撑生产规模数据下的<strong className="text-slate-700">数据一致性排查与 SLA 保障</strong>。
                  </li>
                  <li>
                    修复底层数据管线中图拓扑排序、编码映射、张量传播等多个<strong className="text-slate-700">数据通路一致性问题</strong>，
                    涉及跨算子的 CPU-GPU 数据同步与百万级张量的逐元素诊断。
                  </li>
                </ul>
              </div>

              {/* 项目二：HybriMoE —— 按照腾讯 TEG AI 数据加速 JD 改写 */}
              <div className="relative border-l-2 border-indigo-200 pl-3 transition-colors hover:border-indigo-400">
                <div className="mb-0.5 flex items-start justify-between gap-3">
                  <h3 className="text-[12.5px] font-bold text-slate-900">大模型推理 IO 加速与异构缓存优化（HybriMoE）</h3>
                  <span className="shrink-0 tabular-nums text-[11px] font-medium text-slate-500">2025.05 - 2025.07</span>
                </div>
                <div className="mb-1 text-[11px] font-medium text-indigo-500">C++ / Python / CUDA · 李萌课题组</div>
                <ul className="ml-4 list-disc list-outside space-y-0.5 text-[12px] leading-snug text-slate-600">
                  <li>
                    参与 MoE 大模型推理系统优化，围绕 CPU/GPU 异构设备间的
                    <strong className="text-slate-700">数据搬运、专家加载与 IO 链路</strong>
                    开展 profiling，分析 expert 热冷分布、缓存命中率与端到端延迟之间的关系。
                  </li>
                  <li>
                    提出
                    <strong className="text-slate-700">expert importance-aware mixed-precision scheduling</strong>
                    方案：根据 expert 的访问频率、路由贡献和缓存局部性，为关键 expert 保持高精度、为长尾 expert 采用更低精度，并系统评估量化/反量化开销、带宽占用与推理稳定性的 trade-off。
                  </li>
                </ul>
              </div>

              {/* 项目三：PKU-Get 开源工具 */}
              <div className="relative border-l-2 border-indigo-200 pl-3 transition-colors hover:border-indigo-400">
                <div className="mb-0.5 flex items-start justify-between gap-3">
                  <h3 className="text-[12.5px] font-bold text-slate-900 flex items-center flex-wrap gap-1.5">
                    PKU-Get：北大课程资料一键同步开源工具
                    <Tag variant="success">独立开发 · 百余用户</Tag>
                  </h3>
                  <span className="shrink-0 tabular-nums text-[11px] font-medium text-slate-500">2025.11 - 至今</span>
                </div>
                <div className="mb-1 text-[11px] font-medium text-indigo-500">Python / Selenium / Requests / React / PyWebView / Tailwind CSS</div>
                <ul className="ml-4 list-disc list-outside space-y-0.5 text-[12px] leading-snug text-slate-600">
                  <li>
                    <strong className="text-slate-700">独立完成</strong>从需求定义、爬取链路、桌面端 GUI 到打包发布的全栈开发，
                    面向校内真实场景实现课程资料一键同步；项目已开源，覆盖全校百余名持续使用者。
                  </li>
                  <li>
                    打通 <strong className="text-slate-700">IAAA 登录 / Blackboard 课程平台 / 课堂回放系统</strong> 三套异构链路：
                    通过 Selenium 完成复杂登录与反爬规避，再将浏览器 cookies 与 User-Agent 迁移到 requests Session，
                    实现后续元数据抓取与文件下载的无头化、低开销执行。
                  </li>
                  <li>
                    围绕<strong className="text-slate-700">高脆弱性校园系统兼容</strong>做了大量工程兜底：
                    设计 Chrome / Edge / Firefox / Safari 多浏览器驱动策略与自动修复逻辑，
                    处理 Safari 无 headless、驱动版本不匹配、SSO 跳转链不稳定等问题，保证 Windows / macOS 双平台可用。
                  </li>
                  <li>
                    针对课程回放资源实现<strong className="text-slate-700">JWT 捕获、SSO 会话续接与真实下载地址解析</strong>：
                    通过注入 XHR 拦截脚本、解析 <code className="text-[11px] bg-slate-100 px-1 rounded">playVideo.action</code> 中的 token、复用 IAAA/TGC cookies，
                    解决回放页面跨域、重定向层级深、直链不可直接获取的难点。
                  </li>
                  <li>
                    实现<strong className="text-slate-700">并发下载、去重覆盖策略、同步报告与本地状态持久化</strong>，
                    支持课程别名、标签页筛选、助教课程识别、自动同步与 CLI/GUI 双入口，显著降低用户重复点击与资料整理成本。
                  </li>
                </ul>
              </div>
            </div>
          </section>

          {/* ── 竞赛经历 ── */}
          <section>
            <SectionTitle icon={Swords}>竞赛经历</SectionTitle>
            <div className="space-y-2 pl-1">
              {[
                {
                  name: 'ICCAD Contest 2025',
                  desc: '参与物理设计优化国际竞赛，完成面向大规模图数据的 GPU 加速算法设计、数据管线实现与端到端性能调优。',
                },
                {
                  name: 'ISPD Contest 2026',
                  desc: '参与 post-placement 优化国际竞赛，在合法性、等价性、拥塞与运行时间等多维约束下，设计 GPU 加速的大规模优化方案；beta test 结果超过第二名，final test 待公布。',
                  highlight: true,
                },
              ].map(({ name, desc, highlight }) => (
                <div key={name} className={`pl-3 border-l-2 ${highlight ? 'border-emerald-400' : 'border-indigo-200'}`}>
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className="text-[12.5px] font-bold text-slate-800">{name}</span>
                    
                  </div>
                  <p className="text-[12px] text-slate-600 leading-snug">{desc}</p>
                </div>
              ))}
            </div>
          </section>

          {/* ── 荣誉奖项 ── */}
          <section>
            <SectionTitle icon={Trophy}>荣誉奖项</SectionTitle>
            <ul className="flex flex-wrap gap-1.5 pl-1">
              {[
                '学习优秀奖',
                '三好学生',
                '李惠荣奖学金（5000元）',
                '苏州工业园区奖学金（8000元）',
              ].map(award => (
                <li key={award}>
                  <span className="inline-flex items-center gap-1 bg-amber-50 border border-amber-200 text-amber-800 text-[11.5px] px-2.5 py-0.5 rounded-full font-medium">
                    <Trophy size={10} className="text-amber-500" />
                    {award}
                  </span>
                </li>
              ))}
            </ul>
          </section>

        </div>
      </div>
    </div>
  );
}
