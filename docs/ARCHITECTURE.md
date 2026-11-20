# 架构与责任

员工是原长期对话及持续责任，Skill是员工采用的方法，SDK和运行器是执行组件。

- **共同内核**：每个岗位采用digital-employee，专业能力按任务叠加。
- **横向协作**：codex-thread-handoff传递交办、进展、返修和结果；主责收回后实看，不以转发自述代验收。
- **外部工具**：wechat-aup-control和wechat-write指导员工直接使用实际读写工具；不要求所有发件经另一个AI。wechat-local-read只作授权独立补读。
- **个人工作本**：ROLE保存身份/授权/关系，workbook逐件记责任和判断，CURRENT派生总览，STATE存运行/通信事实，JOURNAL存岗位变化，经验保存带条件的案例。
- **组织共同记事本**：由维护员工用notebook-secretary从授权来源记录组织事项和实际事实，不把个人本拼成另一套竞争主库。
- **人事与维护**：人事维护共同方法、分工和履职复核；工具维护负责共享实现与恢复；业务员工仍负结果责任。

参考部署中，AUP是运行已授权微信小号的Linux工作站，Mac运行Codex判断与编排。组织共享资源是逻辑归属，不预设其必须部署在Mac或AUP。

## 图与源文件

| 视角 | 预览 | 可编辑矢量源 |
|---|---|---|
| A 整体协作 | [PNG](architecture/overview.png) | [SVG](architecture/overview.svg) |
| B 员工内部 | [PNG](architecture/employee.png) | [SVG](architecture/employee.svg) |
| C 任务闭环 | [PNG](architecture/taskflow.png) | [SVG](architecture/taskflow.svg) |

这三张是互补视角，A适合总入口，B/C适合展开。图来自本轮关系梳理，不证明新部署的唤醒、交付或长期稳定性已经验收。

## 任务与工作状态

已承接的任务，无论直接派发、群内交办还是职责内发现并决定承担，都要到真实结果、必要回执与记录，或有明确责任/条件的阻塞。空闲时可以等待，不要求每轮制造新任务。

工作方式（主动、按要求、等反馈、等来源条件、暂不主动、暂停）与任务进度（待推进、等反馈、先放放、已办好、不做了）是两维；状态不会替代交付事实。queued、sourceReady、安装完成和草稿只是相应阶段事实。
