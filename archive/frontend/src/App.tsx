import CodeX from './components/CodeX';

type Lang = 'en' | 'zh';

const COPY = {
  en: {
    pageTitle: "NotionBridge",
    pageSubtitle: "Securely back up your favorite Xiaohongshu notes to your workspace.",
    step1Title: "Connect to Notion",
    step1Desc: "Allow this tool to save pages to your Notion workspace.",
    step1Btn: "Configure Connection",
    step1Verify: "Check Connection",
    step2Title: "Choose Content",
    step2Desc: "Paste the link to the Xiaohongshu collection you want to save.",
    step2Btn: "Check Link",
    step2Advanced: "I need to provide login info (Advanced)",
    step3Title: "Auto-Sync",
    step3Desc: "We will find new items and add them to your database continuously.",
    step3Btn: "Start Auto-Sync Loop",
    step3BtnRunning: "Sync Active (Running in Background)",
    step3BtnStop: "Stop Sync",
    step3Incremental: "Skip items I've already saved",
    step3ClearHistory: "Delete Sync History",
    step3ClearConfirm: "Are you sure? This will force a full re-sync next time.",
    status: {
      notConnected: "Not Connected",
      connected: "Connected",
      waitingLink: "Waiting for Link",
      ready: "Ready to Save",
      running: "Active (Looping)",
      saved: "Saved (Verify needed)",
      linkEntered: "Link Entered",
      validLink: "Valid Link"
    }
  },
  zh: {
    pageTitle: "NotionBridge",
    pageSubtitle: "将你收藏的小红书笔记安全备份到个人工作区。",
    step1Title: "连接 Notion",
    step1Desc: "授权工具访问你的工作区,以便自动创建页面。",
    step1Btn: "配置连接",
    step1Verify: "测试连接",
    step2Title: "选择内容",
    step2Desc: "粘贴你想要备份的小红书收藏夹或专辑链接。",
    step2Btn: "验证链接",
    step2Advanced: "我需要提供登录信息 (高级)",
    step3Title: "自动同步",
    step3Desc: "我们将自动持续检测新笔记并同步到你的数据库。",
    step3Btn: "开始自动同步循环",
    step3BtnRunning: "同步进行中 (后台运行)",
    step3BtnStop: "停止同步",
    step3Incremental: "跳过已保存的笔记",
    step3ClearHistory: "清除同步历史",
    step3ClearConfirm: "确定要清除吗？这将导致下次同步时重新下载所有笔记。",
    status: {
      notConnected: "未连接",
      connected: "已连接",
      waitingLink: "请输入链接",
      ready: "准备就绪",
      running: "运行中 (循环)",
      saved: "已保存 (需验证)",
      linkEntered: "已输入链接",
      validLink: "链接有效"
    }
  }
};

function App() {
  return <CodeX />;
}

export default App;
