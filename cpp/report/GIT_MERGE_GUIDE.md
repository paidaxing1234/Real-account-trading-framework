# Git 合并指南 - Journal框架与前端更新

## 📋 当前情况

- **你的更新**：Journal低延迟通信框架（C++/Python）
- **同事的更新**：前端界面
- **远程仓库**：`git@github.com:paidaxing1234/Real-account-trading-framework.git`

---

## 🎯 推荐方案：功能分支合并

### 步骤1：更新.gitignore（排除build文件）

```bash
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework

# 添加build目录到.gitignore
echo "" >> .gitignore
echo "# Build directories" >> .gitignore
echo "cpp/build/" >> .gitignore
echo "!cpp/build/.gitkeep" >> .gitignore
```

### 步骤2：创建功能分支保存你的工作

```bash
# 创建新分支（基于当前工作）
git checkout -b feature/journal-low-latency

# 添加新文件
git add cpp/core/journal_protocol.h
git add cpp/core/journal_writer.h
git add cpp/core/journal_reader.py
git add cpp/examples/test_journal_*.cpp
git add cpp/examples/test_latency_*.py
git add cpp/examples/test_latency_*.cpp
git add cpp/examples/test_strategy.py
git add cpp/examples/CMakeLists.txt
git add cpp/CMakeLists.txt
git add run_latency_test.sh

# 添加文档
git add README_JOURNAL.md
git add QUICK_START_JOURNAL.md
git add JOURNAL_IMPLEMENTATION_COMPLETE.md
git add 测试报告.md
git add 实现总结.md
git add FILES_CHECKLIST.md
git add Kungfu框架深度分析.md
git add 无锁环形队列.md
git add 无锁环形队列在实盘框架中的应用方案.md

# 更新.gitignore
git add .gitignore

# 提交
git commit -m "feat: 实现Journal低延迟通信框架

- 添加journal_protocol.h（数据协议定义）
- 添加journal_writer.h（C++ Writer，mmap + atomic）
- 添加journal_reader.py（Python Reader，busy loop）
- 添加完整的测试程序（基准测试、延迟测试、策略示例）
- 添加详细文档（架构、快速开始、测试报告等）
- 性能：写入延迟105ns，吞吐量947万事件/秒
- 参考Kungfu框架的无锁设计理念"
```

### 步骤3：拉取同事的最新更改

```bash
# 切换回main分支
git checkout main

# 拉取远程最新代码（包含同事的前端更新）
git pull origin main
```

**如果出现冲突**：
- 仔细查看冲突文件
- 一般前端文件不会和你的C++/Python文件冲突
- 如果有冲突，手动解决后执行：
  ```bash
  git add <冲突文件>
  git commit -m "merge: 解决与前端更新的冲突"
  ```

### 步骤4：合并你的功能分支

```bash
# 将你的Journal功能合并到main
git merge feature/journal-low-latency --no-ff -m "merge: 合并Journal低延迟通信框架

合并功能：
- Journal低延迟通信框架（C++/Python）
- 完整的测试程序和文档
- 性能：105ns延迟，947万事件/秒
- 兼容现有的前端更新"
```

### 步骤5：推送到GitHub

```bash
# 推送main分支
git push origin main

# 推送功能分支（可选，用于备份和协作）
git push origin feature/journal-low-latency
```

---

## 🔍 方案2：直接在main分支提交（简单但不推荐）

如果你确定不会有冲突，可以直接在main分支操作：

```bash
# 1. 先拉取同事的更新
git pull origin main

# 2. 添加并提交你的更改
git add cpp/core/journal_*.h cpp/core/journal_*.py
git add cpp/examples/test_*.cpp cpp/examples/test_*.py
git add *.md run_latency_test.sh
git add cpp/CMakeLists.txt cpp/examples/CMakeLists.txt
git add .gitignore

git commit -m "feat: 实现Journal低延迟通信框架"

# 3. 推送
git push origin main
```

**⚠️ 风险**：如果同事同时也在修改文件，可能会覆盖他的更改。

---

## 🛡️ 方案3：最安全的协作方式（推荐）

### 1. 先备份当前工作

```bash
# 创建备份分支
git checkout -b backup/journal-work-$(date +%Y%m%d)
git add -A
git commit -m "backup: Journal框架完整备份"
git push origin backup/journal-work-$(date +%Y%m%d)
```

### 2. 拉取并查看同事的更改

```bash
# 切换回main
git checkout main

# 拉取最新代码
git fetch origin
git pull origin main

# 查看同事修改了什么
git log --oneline -10
git diff HEAD~5..HEAD --stat
```

### 3. 创建功能分支并合并

```bash
# 创建功能分支
git checkout -b feature/journal-framework

# 从备份分支复制你的更改
git checkout backup/journal-work-$(date +%Y%m%d) -- cpp/core/journal_*
git checkout backup/journal-work-$(date +%Y%m%d) -- cpp/examples/test_*
git checkout backup/journal-work-$(date +%Y%m%d) -- *.md
git checkout backup/journal-work-$(date +%Y%m%d) -- run_latency_test.sh

# 提交
git add -A
git commit -m "feat: 实现Journal低延迟通信框架"

# 切换到main并合并
git checkout main
git merge feature/journal-framework

# 推送
git push origin main
git push origin feature/journal-framework
```

---

## 📊 冲突处理

### 可能的冲突文件

1. **`cpp/CMakeLists.txt`**
   - **原因**：你添加了journal测试程序，同事可能修改了其他配置
   - **解决**：保留两者的修改，手动合并

2. **`README.md`**
   - **原因**：你们可能都修改了文档
   - **解决**：合并内容，或者使用不同的文档文件

3. **前端文件**（如果有）
   - **原因**：同事的前端更新
   - **解决**：保留同事的更改（你没有修改前端）

### 解决冲突步骤

```bash
# 1. 查看冲突文件
git status

# 2. 编辑冲突文件，手动合并
# 查找 <<<<<<< HEAD 和 >>>>>>> 标记
# 保留需要的内容，删除冲突标记

# 3. 标记为已解决
git add <冲突文件>

# 4. 完成合并
git commit -m "merge: 解决合并冲突"
```

---

## 🎯 推荐操作（最安全）

```bash
# === 第一步：备份和清理 ===
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework

# 更新.gitignore
echo -e "\n# Build directories\ncpp/build/\n!cpp/build/.gitkeep" >> .gitignore

# 清理build文件的修改
git restore cpp/build/

# === 第二步：拉取同事的更新 ===
git fetch origin
git pull origin main

# 查看同事做了什么修改
git log --oneline -10

# === 第三步：创建功能分支 ===
git checkout -b feature/journal-low-latency

# 添加你的新文件
git add cpp/core/journal_*.h cpp/core/journal_*.py
git add cpp/examples/test_journal_* cpp/examples/test_latency_* cpp/examples/test_strategy.py
git add cpp/examples/CMakeLists.txt
git add cpp/CMakeLists.txt
git add *.md run_latency_test.sh .gitignore

# 提交
git commit -m "feat: 实现Journal低延迟通信框架

核心功能：
- journal_protocol.h: 数据协议定义
- journal_writer.h: C++ Writer（mmap + atomic）
- journal_reader.py: Python Reader（busy loop）
- 完整测试程序：基准测试、延迟测试、策略示例
- 详细文档：架构、快速开始、测试报告

性能指标：
- 写入延迟：105ns
- 吞吐量：947万事件/秒
- 端到端延迟：<1μs

技术特点：
- 零拷贝设计
- 无锁通信
- 基于Kungfu框架理念
- 完整的测试和文档"

# === 第四步：合并到main ===
git checkout main
git merge feature/journal-low-latency --no-ff

# === 第五步：推送 ===
git push origin main
git push origin feature/journal-low-latency
```

---

## 📝 提交信息规范

使用规范的提交信息格式：

```
feat: 实现Journal低延迟通信框架

- 添加核心实现文件（3个）
- 添加测试程序（5个）
- 添加完整文档（6个）
- 性能：105ns延迟，947万事件/秒

Closes #<issue_number>
```

---

## ⚠️ 注意事项

1. **先拉取，后推送**
   - 永远先 `git pull`，再 `git push`
   - 避免覆盖同事的工作

2. **排除build文件**
   - build目录不应该提交到Git
   - 使用.gitignore排除

3. **功能分支**
   - 大型功能使用独立分支开发
   - 合并时使用 `--no-ff` 保留分支历史

4. **提交前检查**
   ```bash
   git status        # 查看修改
   git diff          # 查看具体改动
   git diff --cached # 查看暂存的改动
   ```

5. **推送前测试**
   - 确保代码可以编译
   - 运行测试确保功能正常
   ```bash
   cd cpp/build
   cmake .. && make -j4
   ./test_journal_benchmark
   ```

---

## 🚨 紧急回滚

如果推送后发现问题：

```bash
# 查看历史
git log --oneline -10

# 回滚到某个提交
git reset --hard <commit_hash>

# 强制推送（慎用！）
git push origin main --force
```

**⚠️ 警告**：`--force` 会覆盖远程历史，只在确定没有其他人在使用时使用。

---

## 📞 需要帮助？

- 查看Git状态：`git status`
- 查看提交历史：`git log --oneline --graph --all`
- 查看远程分支：`git branch -r`
- 查看所有分支：`git branch -a`

---

**建议**：先在本地测试合并，确保没有问题后再推送到远程！

