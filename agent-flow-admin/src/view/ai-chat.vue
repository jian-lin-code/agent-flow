<template>
  <div class="ai-chat-container">
    <!-- 左侧：最近会话列表 -->
    <aside class="chat-sessions-sidebar">
      <div class="sidebar-header">
        <span class="sidebar-title"><el-icon><ChatDotRound /></el-icon> {{ $t('chat.recentSessions') }}</span>
        <button class="new-chat-btn" :aria-label="$t('chat.newSession')" @click="startNewChat"><el-icon><Plus /></el-icon></button>
      </div>
      <div class="session-search">
        <el-icon><Search /></el-icon>
        <input
          v-model="sessionKeyword"
          type="text"
          maxlength="50"
          :placeholder="$t('chat.searchSessions')"
          @keydown.esc="clearSearch"
        />
        <el-icon v-if="searching" class="is-loading search-spin"><Loading /></el-icon>
        <button
          v-else-if="isSearchMode"
          class="search-clear"
          type="button"
          :title="$t('chat.clearSearch')"
          :aria-label="$t('chat.clearSearch')"
          @click="clearSearch"
        >
          <el-icon><Close /></el-icon>
        </button>
      </div>
      <div v-if="isSearchMode && !searching && displaySessions.length" class="search-meta">
        <span>{{ $t('chat.searchResultCount', { count: searchTotal || displaySessions.length }) }}</span>
        <span v-if="searchTotal > displaySessions.length" class="search-meta-more">
          {{ $t('chat.searchResultLimited', { shown: displaySessions.length }) }}
        </span>
      </div>
      <div class="session-list">
        <div
          v-for="session in displaySessions"
          :key="session.uid"
          class="session-item"
          :class="{ active: currentSessionId === session.uid, editing: editingUid === session.uid }"
          @click="handleSelectSession(session.uid)"
        >
          <!-- 行内重命名：回车保存、Esc 取消、失焦保存 -->
          <div v-if="editingUid === session.uid" class="session-rename" @click.stop>
            <input
              :ref="(el) => setRenameInput(el)"
              v-model="editingTitle"
              class="session-rename-input"
              type="text"
              maxlength="20"
              :placeholder="$t('chat.renamePlaceholder')"
              @keydown.enter.prevent="commitRename(session)"
              @keydown.esc.prevent="cancelRename"
              @blur="commitRename(session)"
            />
          </div>
          <template v-else>
            <div class="session-info">
              <div class="session-name" :title="session.name" @dblclick.stop="beginRename(session)">
                <template v-for="(part, i) in highlightParts(session.name)" :key="i">
                  <mark v-if="part.match" class="session-hit">{{ part.text }}</mark>
                  <template v-else>{{ part.text }}</template>
                </template>
              </div>
              <div class="session-preview">{{ session.time }}</div>
            </div>
            <div class="session-actions">
              <button
                class="session-action-btn"
                type="button"
                :title="$t('chat.renameSession')"
                :aria-label="$t('chat.renameSession')"
                @click.stop="beginRename(session)"
              >
                <el-icon><Edit /></el-icon>
              </button>
              <button
                class="session-action-btn danger"
                type="button"
                :title="$t('chat.deleteSession')"
                :aria-label="$t('chat.deleteSession')"
                @click.stop="handleDeleteSession(session)"
              >
                <el-icon><Delete /></el-icon>
              </button>
            </div>
          </template>
        </div>

        <!-- 没有任何会话时的引导 -->
        <div v-if="sessions.length === 0 && !isSearchMode" class="session-empty-state">
          <div class="empty-illustration">
            <el-icon><ChatDotRound /></el-icon>
          </div>
          <p class="empty-title">{{ $t('chat.noSessionsTitle') }}</p>
          <p class="empty-desc">{{ $t('chat.noSessionsDesc') }}</p>
        </div>
        <!-- 搜索请求进行中且暂无结果 -->
        <div v-else-if="isSearchMode && searching && displaySessions.length === 0" class="session-empty">
          {{ $t('chat.searching') }}
        </div>
        <!-- 有会话但搜索无匹配 -->
        <div v-else-if="isSearchMode && !searching && displaySessions.length === 0" class="session-empty">
          {{ $t('chat.noMatchSessions') }}
          <button class="empty-clear" type="button" @click="clearSearch">{{ $t('chat.clearSearch') }}</button>
        </div>
      </div>
      <div class="sidebar-foot"><span class="dot green" /> {{ $t('chat.quota') }} 4 / 50</div>
    </aside>

    <!-- 中间：聊天主区域 -->
    <div class="chat-main-area">
      <!-- 移动端：悬浮在聊天区左上角的会话入口，不占独立顶栏 -->
      <button
        class="mobile-sessions-fab"
        type="button"
        :aria-label="$t('chat.recentSessions')"
        :title="$t('chat.recentSessions')"
        @click="sessionsDrawer = true"
      >
        {{ $t('chat.sessionsShort') }}
        <el-icon class="fab-arrow"><ArrowRight /></el-icon>
      </button>

      <div class="chat-header">
        <div class="header-left">
          <h2 class="chat-title">
            {{ activeSession?.name || $t('chat.newConversation') }}
            <el-icon
              v-if="activeSession"
              class="edit-icon"
              :title="$t('chat.renameSession')"
              @click="renameActiveSession"
            ><Edit /></el-icon>
          </h2>
        </div>
        <div class="chat-tag"><span class="dot green" /> {{ $t('chat.aiOnline') }}</div>
      </div>

      <div class="chat-messages" ref="messageScroll" @scroll.passive="updateNearBottom">
        <div v-if="messages.length === 0" class="chat-welcome">
          <div class="welcome-icon"><el-icon><Service /></el-icon></div>
          <h3>{{ $t('chat.welcomeGreet') }}</h3>
          <p>{{ $t('chat.welcomeHint') }}</p>
          <!-- 新手引导：点击直接发送，零成本上手 -->
          <div class="welcome-suggestions">
            <button
              v-for="(suggestion, i) in welcomeSuggestions"
              :key="i"
              type="button"
              class="welcome-chip"
              :disabled="loading || hasActiveRun"
              @click="sendUserMessage(suggestion)"
            >
              <el-icon :size="13"><ChatDotRound /></el-icon>
              <span>{{ suggestion }}</span>
            </button>
          </div>
        </div>
        <div v-for="(msg, index) in messages" :key="index" class="message-wrapper" :class="msg.role">
          <div class="message-avatar">
            <div class="avatar-badge" :class="msg.role">
              <el-icon v-if="msg.role === 'ai'"><Service /></el-icon>
              <template v-else>{{ avatarText }}</template>
            </div>
          </div>
          <div class="message-content-group">
            <div class="message-meta">
              <span class="message-author">{{ msg.role === 'ai' ? $t('chat.welcomeTitle') : $t('chat.you') }}</span>
              <span class="llm-tag" v-if="msg.role === 'ai'">LLM-v2.5</span>
              <span class="message-time">{{ msg.time }}</span>
            </div>
            <div class="message-content">
              <!-- 纯文本内容（只有卡片、没有正文的消息不渲染空气泡）；AI 消息按 Markdown 渲染 -->
              <div v-if="msg.type === 'text' && (!!msg.content || msg.streaming)" class="text-box" :class="{ 'md-body': msg.role === 'ai' }">
                <div v-if="msg.role === 'ai'" class="md-content" v-html="renderMarkdown(msg.content)"></div>
                <template v-else>{{ msg.content }}</template>
                <span v-if="msg.streaming" class="typing-caret" />
              </div>

              <!-- 表格内容 -->
              <div v-else-if="msg.type === 'table'" class="table-box">
                <div class="table-title">{{ msg.tableTitle }}</div>
                <el-table :data="msg.tableData" style="width: 100%" size="small" border>
                  <el-table-column v-for="col in msg.columns" :key="col.prop" :prop="col.prop" :label="col.label" />
                  <el-table-column :label="$t('common.actions')" width="80">
                    <template #default>
                      <el-link type="primary" :underline="false">{{ $t('employee.viewDetail') }}</el-link>
                    </template>
                  </el-table-column>
                </el-table>
                <div class="table-footer">{{ msg.tableFooter }}</div>
              </div>

              <!-- 详情卡片内容 -->
              <div v-else-if="msg.type === 'detail-card'" class="detail-card">
                <div class="card-header">
                  <el-icon class="card-icon"><Document /></el-icon>
                  <span class="card-title">{{ msg.cardTitle }}</span>
                  <el-tag size="small" type="warning" effect="plain" class="card-tag">{{ $t('employee.stApproving') }}</el-tag>
                </div>
                <div class="card-body" v-if="msg.details">
                  <div class="info-row">
                    <div class="info-item"><span class="label">{{ $t('chat.labelApplicant') }}</span><span class="value">{{ msg.details.applicant }}</span></div>
                    <div class="info-item"><span class="label">{{ $t('chat.labelExpenseType') }}</span><span class="value">{{ msg.details.type }}</span></div>
                  </div>
                  <div class="info-row">
                    <div class="info-item"><span class="label">{{ $t('chat.labelTripTime') }}</span><span class="value">{{ msg.details.dateRange }}</span></div>
                    <div class="info-item"><span class="label">{{ $t('chat.labelAttachments') }}</span><span class="value">{{ msg.details.attachments }}</span></div>
                  </div>
                  <div class="info-row">
                    <div class="info-item"><span class="label">{{ $t('chat.labelLocation') }}</span><span class="value">{{ msg.details.location }}</span></div>
                    <div class="info-item"><span class="label">{{ $t('chat.labelApplyTime') }}</span><span class="value">{{ msg.details.applyTime }}</span></div>
                  </div>
                  <div class="info-row">
                    <div class="info-item"><span class="label">{{ $t('chat.labelAmount') }}</span><span class="value amount">￥ {{ msg.details.amount }}</span></div>
                    <div class="info-item"><span class="label">{{ $t('chat.labelApprover') }}</span><span class="value">{{ msg.details.approver }}</span></div>
                  </div>
                </div>
                <div class="card-footer">
                  <el-link type="primary" :underline="false">{{ $t('chat.viewFullFlow') }} ></el-link>
                </div>
              </div>

              <!-- 操作按钮 -->
              <div v-if="msg.actions" class="action-buttons">
                <button v-for="btn in msg.actions" :key="btn" class="suggest-btn">{{ btn }}</button>
              </div>

              <!-- 知识库引用来源卡片：数据来自 extra_data（ui_type = knowledge_sources） -->
              <div
                v-if="msg.role === 'ai' && knowledgeSourceGroups(msg.extraData).length"
                class="ks-card"
              >
                <div
                  v-for="group in knowledgeSourceGroupsList(msg.extraData)[0]"
                  :key="group.title"
                  class="ks-group"
                  :class="{ expanded: isKsExpanded(msg, group.title) }"
                >
                  <button class="ks-doc" type="button" @click="toggleKsGroup(msg, group.title)">
                    <el-icon class="ks-doc-icon"><Document /></el-icon>
                    <span class="ks-doc-title" :title="group.title">《{{ group.title }}》</span>
                    <span v-if="group.kbName" class="ks-kb" :title="group.kbName">{{ group.kbName }}</span>
                    <el-icon class="ks-caret"><component :is="isKsExpanded(msg, group.title) ? CaretBottom : CaretRight" /></el-icon>
                  </button>
                  <div v-show="isKsExpanded(msg, group.title)" class="ks-rows">
                    <button
                      v-for="(src, i) in group.items"
                      :key="`${group.title}-${src.index ?? i}`"
                      type="button"
                      class="ks-row"
                      :class="{ 'is-link': canJumpSource(src) }"
                      :disabled="!canJumpSource(src)"
                      :title="canJumpSource(src) ? $t('chat.sourceJumpHint') : ''"
                      @click="jumpToSource(src)"
                    >
                      <span class="ks-branch">{{ i === group.items.length - 1 ? '└' : '├' }}</span>
                      <span class="ks-index">[{{ src.index ?? i + 1 }}]</span>
                      <span class="ks-location">{{ src.location || '-' }}</span>
                      <el-icon v-if="canJumpSource(src)" class="ks-jump"><ArrowRight /></el-icon>
                    </button>
                  </div>
                </div>
              </div>

              <!-- 业务任务卡片：数据来自消息 extra_data，不解析 AI 回复文本 -->
              <div
                v-if="msg.role === 'ai' && taskListOf(msg.extraData).length"
                class="task-card-list"
              >
                <button
                  v-for="task in taskListOf(msg.extraData)"
                  :key="task.uid"
                  type="button"
                  class="task-card"
                  :class="{ selected: selectingTaskUid === task.uid }"
                  :disabled="selectingTaskUid !== null || loading || hasActiveRun"
                  @click="handleSelectBusinessTask(task, msg.extraData)"
                >
                  <span class="task-card-avatar"><el-icon><Tickets /></el-icon></span>
                  <div class="task-card-body">
                    <div class="task-card-head">
                      <span class="task-card-title">{{ task.title }}</span>
                      <span class="task-card-status" :class="task.status">{{ taskStatusLabel(task.status) }}</span>
                    </div>
                    <!-- 摘要行：金额 · 笔数 · 类别 · 日期，让用户能区分列表里的每笔报销 -->
                    <div class="task-card-summary">
                      <span class="task-sum-amount">
                        {{ formatMoney(task.display?.total_amount, task.display?.currency) }}
                      </span>
                      <span class="task-sum-meta">{{ taskListMeta(task) }}</span>
                    </div>
                    <div v-if="task.missing_fields?.length" class="task-card-missing">
                      <span class="task-missing-label">{{ $t('chat.taskMissingCount', { count: task.missing_fields.length }) }}</span>
                    </div>
                    <div class="task-card-foot">
                      <el-icon v-if="selectingTaskUid === task.uid" class="is-loading task-card-loading"><Loading /></el-icon>
                      <span>{{ selectingTaskUid === task.uid ? $t('chat.taskSelecting') : $t('chat.taskSelect') }}</span>
                      <el-icon class="task-card-arrow"><ArrowRight /></el-icon>
                    </div>
                  </div>
                </button>
              </div>

              <!-- 当前任务卡片：展示任务摘要 + 费用明细（数据来自 display / draft_data） -->
              <div v-else-if="msg.role === 'ai' && taskOf(msg.extraData)" class="task-detail">
                <div class="td-head">
                  <span class="td-avatar"><el-icon><Tickets /></el-icon></span>
                  <div class="td-head-main">
                    <div class="td-title-row">
                      <span class="td-title">{{ taskView(msg).title }}</span>
                      <span class="task-card-status" :class="taskView(msg).status">
                        {{ taskStatusLabel(taskView(msg).status) }}
                      </span>
                      <span v-if="taskView(msg).claimStatus" class="td-claim">
                        {{ $t('chat.claimStatusPrefix') }} {{ claimStatusLabel(taskView(msg).claimStatus) }}
                      </span>
                    </div>
                    <!-- 任务 UID：过长时省略，点击复制完整值 -->
                    <button
                      type="button"
                      class="td-uid"
                      :title="$t('chat.taskCopyUid')"
                      @click="copyText(taskView(msg).uid)"
                    >
                      <span class="td-uid-label">{{ $t('chat.taskUid') }}</span>
                      <span class="td-uid-value">{{ taskView(msg).uid }}</span>
                      <el-icon class="td-uid-icon"><CopyDocument /></el-icon>
                    </button>
                  </div>
                </div>

                <!-- 金额 / 明细数 / 创建时间 -->
                <div class="td-stats">
                  <div class="td-stat">
                    <span class="td-stat-label">{{ $t('chat.taskTotalAmount') }}</span>
                    <span class="td-stat-value primary">{{ taskView(msg).totalText }}</span>
                  </div>
                  <div class="td-stat">
                    <span class="td-stat-label">{{ $t('chat.taskItemCount') }}</span>
                    <span class="td-stat-value">{{ taskView(msg).itemCount }} {{ $t('chat.taskItemUnit') }}</span>
                  </div>
                  <div class="td-stat">
                    <span class="td-stat-label">{{ taskView(msg).claimNo ? $t('chat.taskClaimNo') : $t('chat.taskCreatedAt') }}</span>
                    <span class="td-stat-value small">{{ taskView(msg).claimNo || taskView(msg).createdAtText }}</span>
                  </div>
                </div>

                <!-- 费用明细 -->
                <div class="td-section">
                  <div class="td-section-head">
                    <span class="td-section-title">{{ $t('chat.taskExpenseDetail') }}</span>
                    <span class="td-section-count">{{ taskView(msg).itemCount }}</span>
                  </div>
                  <div v-if="!taskView(msg).items.length" class="td-empty">
                    {{ $t('chat.taskNoExpenseItems') }}
                  </div>
                  <div v-else class="td-items">
                    <div v-for="(item, idx) in taskView(msg).items" :key="item.id" class="td-item">
                      <span class="td-item-index">{{ idx + 1 }}</span>
                      <div class="td-item-main">
                        <div class="td-item-line">
                          <span class="td-item-desc">{{ item.description }}</span>
                          <span class="td-item-amount" :class="{ missing: item.amountMissing }">{{ item.amountText }}</span>
                        </div>
                        <div class="td-item-meta">
                          <span class="td-chip" :class="{ missing: item.categoryMissing }">{{ item.categoryText }}</span>
                          <span class="td-item-date" :class="{ missing: item.dateMissing }">{{ item.dateText }}</span>
                          <!-- 发票：至少一张；未上传显示上传按钮，已上传显示数量 -->
                          <span
                            v-if="item.invoiceCount > 0"
                            class="td-invoice-ok"
                            :title="item.invoiceFileNames.join('\n') || undefined"
                          >
                            <el-icon><CircleCheck /></el-icon>
                            {{ $t('chat.invoiceUploadedCount', { count: item.invoiceCount }) }}
                          </span>
                          <!-- 上传入口：按钮上覆盖一个透明的 file input。
                               用原生点击直接触发选择器，不依赖 JS 里 input.click()，
                               规避移动端 WebView 对 display:none 输入框不触发 change 的问题 -->
                          <span v-if="item.invoiceMissing" class="td-invoice-uploader">
                            <button
                              type="button"
                              class="td-invoice-btn"
                              :class="{ ghost: item.invoiceCount > 0 }"
                              :disabled="uploadingItemUid === item.id || !canUploadInvoice(taskView(msg).status)"
                              :title="canUploadInvoice(taskView(msg).status) ? $t('chat.invoiceUploadHint') : $t('chat.invoiceUploadLocked')"
                            >
                              <el-icon v-if="uploadingItemUid === item.id" class="is-loading"><Loading /></el-icon>
                              <el-icon v-else><Upload /></el-icon>
                              {{ uploadingItemUid === item.id ? $t('chat.invoiceUploading') : $t('chat.invoiceUpload') }}
                            </button>
                            <input
                              v-if="canUploadInvoice(taskView(msg).status) && uploadingItemUid !== item.id"
                              class="td-invoice-input"
                              type="file"
                              :accept="INVOICE_ACCEPT"
                              :multiple="!isMobileViewport"
                              :title="$t('chat.invoiceUploadHint')"
                              :aria-label="$t('chat.invoiceUpload')"
                              @change="onInvoiceFileChange($event, msg, item)"
                            />
                          </span>
                          <span v-if="item.missingLabels.length" class="td-item-warn">
                            {{ $t('chat.taskMissingInline', { fields: item.missingLabels.join('、') }) }}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 待补充汇总 / 信息完整 -->
                <div v-if="taskView(msg).missingCount" class="td-alert">
                  <el-icon><WarningFilled /></el-icon>
                  <span>
                    {{ taskView(msg).missingLabelsText
                      ? $t('chat.taskMissingSummary', {
                          count: taskView(msg).missingCount,
                          fields: taskView(msg).missingLabelsText
                        })
                      : $t('chat.taskMissingCount', { count: taskView(msg).missingCount }) }}
                  </span>
                </div>
                <div v-else class="td-ok">
                  <el-icon><CircleCheck /></el-icon>
                  <span>{{ $t('chat.taskAllFilled') }}</span>
                </div>
              </div>

              <!-- 报销记录列表卡片：数据来自 extra_data（ui_type = expense_claim_list），不解析正文 -->
              <div
                v-if="msg.role === 'ai' && claimPayloadOf(msg.extraData)"
                class="claim-card"
              >
                <div class="claim-card-head">
                  <span class="claim-card-title">
                    <el-icon><Tickets /></el-icon>
                    {{ $t('chat.claimListTitle') }}
                  </span>
                  <span class="claim-card-count">
                    {{ $t('chat.claimListTotal', { count: claimPagerOf(msg.extraData).total }) }}
                  </span>
                </div>

                <!-- 空状态：接口无记录 -->
                <div v-if="!claimRowsOf(msg.extraData).length" class="claim-empty">
                  {{ $t('chat.claimListEmpty') }}
                </div>
                <template v-else>
                  <button
                    v-for="claim in claimRowsOf(msg.extraData)"
                    :key="claim.claim_no"
                    type="button"
                    class="claim-row"
                    @click="openClaimDetail(claim)"
                  >
                    <div class="claim-row-main">
                      <div class="claim-row-top">
                        <span class="claim-row-no">{{ claim.claim_no }}</span>
                        <span class="claim-status" :class="claimStatusClass(claim.status)">
                          {{ claimStatusLabel(claim.status) }}
                        </span>
                      </div>
                      <div class="claim-row-title">{{ claim.title || $t('chat.claimUntitled') }}</div>
                      <div class="claim-row-meta">
                        <span class="claim-row-amount">{{ formatMoney(claim.total_amount, claim.currency) }}</span>
                        <template v-if="claim.categories?.length">
                          <span class="claim-row-sep">·</span>
                          <span class="claim-row-cats">{{ claim.categories.join(' / ') }}</span>
                        </template>
                        <span v-if="claim.descriptions?.length" class="claim-row-desc">
                          · {{ claim.descriptions.join('，') }}
                        </span>
                      </div>
                      <div class="claim-row-time">
                        {{ $t('chat.claimSubmittedAt') }} {{ formatClaimTime(claim.submitted_at) }}
                      </div>
                    </div>
                    <el-icon class="claim-row-arrow"><ArrowRight /></el-icon>
                  </button>

                  <!-- 分页信息（翻页由用户在聊天输入「上一页/下一页」完成，不提供点击翻页） -->
                  <div class="claim-pager">
                    <span class="claim-pager-info">
                      {{ $t('chat.claimPagerInfo', {
                        page: claimPagerOf(msg.extraData).page,
                        pages: claimPagerOf(msg.extraData).totalPages,
                        total: claimPagerOf(msg.extraData).total
                      }) }}
                    </span>
                  </div>
                  <div class="claim-pager-hint">{{ $t('chat.claimPagerHint') }}</div>
                </template>
              </div>

              <!-- 报销单详情卡片：数据来自 extra_data（ui_type = expense_claim_detail） -->
              <div
                v-if="msg.role === 'ai' && claimDetailView(msg.extraData)"
                class="claim-card claim-detail-card"
              >
                <template v-for="view in asList(claimDetailView(msg.extraData))" :key="`cd-${view.claim.claim_no}`">
                  <div class="claim-card-head">
                    <span class="claim-card-title">
                      <el-icon><Tickets /></el-icon>
                      {{ $t('chat.claimDetailTitle') }}
                    </span>
                    <span class="claim-status" :class="claimStatusClass(view.claim.status)">
                      {{ claimStatusLabel(view.claim.status) }}
                    </span>
                  </div>

                  <!-- 单号 / 标题 / 描述 -->
                  <div class="cd-head">
                    <span class="cd-no">{{ view.claim.claim_no }}</span>
                    <div class="cd-title">{{ view.claim.title || $t('chat.claimUntitled') }}</div>
                    <div v-if="view.claim.description" class="cd-desc">{{ view.claim.description }}</div>
                  </div>

                  <!-- 摘要：总金额 + 类别 + 时间 -->
                  <div class="cd-summary">
                    <div class="cd-amount">
                      <span class="cd-amount-label">{{ $t('chat.claimDetailTotal') }}</span>
                      <span class="cd-amount-value">
                        {{ formatMoney(claimItemsSum(view.claim), view.claim.currency) }}
                      </span>
                    </div>
                    <div class="cd-summary-meta">
                      <div class="cd-meta-row">
                        <span class="cd-meta-label">{{ $t('chat.fieldCategory') }}</span>
                        <span class="cd-meta-value">{{ view.claim.categories?.join(' / ') || '-' }}</span>
                      </div>
                      <div class="cd-meta-row">
                        <span class="cd-meta-label">{{ $t('chat.claimSubmittedAt') }}</span>
                        <span class="cd-meta-value">{{ formatClaimTime(view.claim.submitted_at) }}</span>
                      </div>
                      <div class="cd-meta-row">
                        <span class="cd-meta-label">{{ $t('chat.claimDetailUpdated') }}</span>
                        <span class="cd-meta-value">{{ formatClaimTime(view.claim.updated_at) }}</span>
                      </div>
                    </div>
                  </div>

                  <!-- 费用明细 -->
                  <div class="cd-section">
                    <div class="cd-section-title">
                      {{ $t('chat.claimDetailItems') }}
                      <span class="cd-section-count">{{ $t('chat.claimDetailItemsTotal', { count: view.items.length }) }}</span>
                    </div>
                    <div v-if="!view.items.length" class="cd-empty">{{ $t('chat.claimDetailNoItems') }}</div>
                    <div v-else class="cd-items">
                      <div v-for="item in view.items" :key="item.id ?? `${item.category}-${item.description}`" class="cd-item">
                        <span class="cd-item-cat">{{ item.category || '-' }}</span>
                        <span class="cd-item-desc">{{ item.description || '-' }}</span>
                        <span class="cd-item-date">{{ formatClaimDate(item.expense_date) }}</span>
                        <span class="cd-item-amount">{{ formatMoney(item.amount, view.claim.currency) }}</span>
                      </div>
                    </div>
                  </div>

                  <!-- AI 预审 -->
                  <div class="cd-section">
                    <div class="cd-section-title">{{ $t('chat.claimDetailPreReview') }}</div>
                    <div v-if="!view.claim.pre_review" class="cd-empty">{{ $t('chat.claimDetailNoPreReview') }}</div>
                    <div v-else class="cd-pr">
                      <div class="cd-pr-head">
                        <span class="claim-status" :class="claimPreReviewClass(view.claim.pre_review)">
                          {{ claimPreReviewLabel(view.claim.pre_review) }}
                        </span>
                        <span
                          v-if="view.claim.pre_review.risk_level"
                          class="claim-status"
                          :class="preReviewRiskClass(view.claim.pre_review.risk_level)"
                        >
                          {{ preReviewRiskLabel(view.claim.pre_review.risk_level) }}
                        </span>
                      </div>
                      <div v-if="view.claim.pre_review.summary" class="cd-pr-summary">
                        {{ view.claim.pre_review.summary }}
                      </div>
                    </div>
                  </div>

                  <!-- 审批记录 -->
                  <div class="cd-section">
                    <div class="cd-section-title">
                      {{ $t('chat.claimDetailApprovals') }}
                      <span class="cd-section-count">{{ view.approvals.length }}</span>
                    </div>
                    <div v-if="!view.approvals.length" class="cd-empty">{{ $t('chat.claimDetailNoApprovals') }}</div>
                    <div v-else class="cd-approvals">
                      <div v-for="(ap, idx) in view.approvals" :key="idx" class="cd-approval">
                        <div class="cd-approval-head">
                          <span class="claim-status" :class="claimApprovalClass(ap)">
                            {{ claimApprovalLabel(ap) }}
                          </span>
                          <span class="cd-approval-approver">{{ claimApproverName(ap) }}</span>
                          <span class="cd-approval-time">{{ formatClaimTime(ap.decided_at) }}</span>
                        </div>
                        <div v-if="ap.comment" class="cd-approval-comment">{{ ap.comment }}</div>
                      </div>
                    </div>
                  </div>

                  <!-- 发票凭证 -->
                  <div class="cd-section">
                    <div class="cd-section-title">
                      {{ $t('chat.claimDetailAttachments') }}
                      <span class="cd-section-count">{{ view.attachments.length }}</span>
                    </div>
                    <div v-if="!view.attachments.length" class="cd-empty">{{ $t('chat.claimDetailNoAttachments') }}</div>
                    <div v-else class="cd-atts">
                      <span v-for="(att, idx) in view.attachments" :key="idx" class="cd-att">
                        <el-icon><Paperclip /></el-icon>
                        {{ att.original_filename || $t('chat.claimDetailAttachmentFallback') }}
                      </span>
                    </div>
                  </div>

                  <!-- 打开完整详情抽屉 -->
                  <div class="cd-footer">
                    <button type="button" class="cd-open" @click="openClaimDetail(view.claim)">
                      {{ $t('chat.claimDetailOpen') }}
                      <el-icon><ArrowRight /></el-icon>
                    </button>
                  </div>
                </template>
              </div>

              <!-- 报销审批进度卡片：数据来自 extra_data（ui_type = expense_progress），垂直时间线 -->
              <div
                v-if="msg.role === 'ai' && progressView(msg.extraData)"
                class="claim-card progress-card"
              >
                <template v-for="prog in asList(progressView(msg.extraData))" :key="`pg-${prog.claim_no}`">
                  <div class="claim-card-head">
                    <span class="claim-card-title">
                      <el-icon><Timer /></el-icon>
                      {{ $t('chat.progressTitle') }}
                    </span>
                    <span class="claim-status" :class="claimStatusClass(prog.status)">
                      {{ claimStatusLabel(prog.status) }}
                    </span>
                  </div>

                  <!-- 单号 / 标题 / 金额 -->
                  <div class="cd-head pg-head">
                    <div class="pg-head-left">
                      <span class="cd-no">{{ prog.claim_no }}</span>
                      <div class="cd-title">{{ prog.title || $t('chat.claimUntitled') }}</div>
                    </div>
                    <div class="pg-head-amount">
                      {{ formatMoney(prog.total_amount, prog.currency) }}
                    </div>
                  </div>

                  <!-- 审批进度时间线 -->
                  <div class="cd-timeline">
                    <!-- 节点 1：提交申请 -->
                    <div class="cd-tl-node">
                      <span class="cd-tl-dot" :class="progressDotClass()" />
                      <div class="cd-tl-body">
                        <div class="cd-tl-row">
                          <span class="cd-tl-label">{{ $t('chat.progressSubmitted') }}</span>
                          <span class="cd-tl-time">{{ formatClaimTime(prog.submitted_at) }}</span>
                        </div>
                      </div>
                    </div>

                    <!-- 节点 N：人工审批记录 -->
                    <div
                      v-for="(ap, idx) in prog.approvals"
                      :key="ap.id ?? idx"
                      class="cd-tl-node"
                    >
                      <span class="cd-tl-dot" :class="progressDotClass(ap)" />
                      <div class="cd-tl-body">
                        <div class="cd-tl-row">
                          <span class="claim-status" :class="claimApprovalClass(ap)">
                            {{ claimApprovalLabel(ap) }}
                          </span>
                          <span class="cd-tl-approver">{{ claimProgressApproverName(ap) }}</span>
                          <span class="cd-tl-time">{{ formatClaimTime(ap.decided_at || ap.created_at) }}</span>
                        </div>
                        <div v-if="ap.comment" class="cd-approval-comment">{{ ap.comment }}</div>
                      </div>
                    </div>

                    <!-- 等待审批：单据仍在流转时的当前节点 -->
                    <div v-if="progressWaiting(prog)" class="cd-tl-node">
                      <span class="cd-tl-dot tl-wait" />
                      <div class="cd-tl-body">
                        <div class="cd-tl-row">
                          <span class="cd-tl-label tl-wait-label">{{ $t('chat.progressWaiting') }}</span>
                        </div>
                        <div v-if="!prog.approvals.length" class="cd-tl-hint">
                          {{ $t('chat.progressNoApprovals') }}
                        </div>
                      </div>
                    </div>
                  </div>
                </template>
              </div>

              <!-- 报销审批历史卡片：数据来自 extra_data（ui_type = expense_approval_history），回顾型时间线 -->
              <div
                v-if="msg.role === 'ai' && historyView(msg.extraData)"
                class="claim-card history-card"
              >
                <template v-for="h in asList(historyView(msg.extraData))" :key="`ah-${h.claim_no}`">
                  <div class="claim-card-head">
                    <span class="claim-card-title">
                      <el-icon><Clock /></el-icon>
                      {{ $t('chat.historyTitle') }}
                    </span>
                    <span class="claim-status" :class="claimStatusClass(h.status)">
                      {{ claimStatusLabel(h.status) }}
                    </span>
                  </div>

                  <!-- 单号 / 标题 / 金额 -->
                  <div class="cd-head pg-head">
                    <div class="pg-head-left">
                      <span class="cd-no">{{ h.claim_no }}</span>
                      <div class="cd-title">{{ h.title || $t('chat.claimUntitled') }}</div>
                    </div>
                    <div class="pg-head-amount">
                      {{ formatMoney(h.total_amount, h.currency) }}
                    </div>
                  </div>

                  <!-- 审批历史时间线（只回顾已发生的记录，无等待节点） -->
                  <div class="cd-timeline">
                    <div v-if="!h.approvals.length" class="cd-empty">
                      {{ $t('chat.historyNoRecords') }}
                    </div>
                    <div
                      v-for="(ap, idx) in h.approvals"
                      :key="ap.id ?? idx"
                      class="cd-tl-node"
                    >
                      <span class="cd-tl-dot" :class="progressDotClass(ap)" />
                      <div class="cd-tl-body">
                        <div class="cd-tl-row">
                          <span class="claim-status" :class="claimApprovalClass(ap)">
                            {{ claimApprovalLabel(ap) }}
                          </span>
                          <span class="cd-tl-approver">{{ claimProgressApproverName(ap) }}</span>
                          <span class="cd-tl-time">{{ formatClaimTime(ap.decided_at || ap.created_at) }}</span>
                        </div>
                        <div v-if="ap.comment" class="cd-approval-comment">{{ ap.comment }}</div>
                      </div>
                    </div>
                    <div v-if="h.approvals.length" class="cd-tl-summary">
                      {{ $t('chat.historyCount', { count: h.approvals.length }) }}
                    </div>
                  </div>
                </template>
              </div>

              <!-- 报销 AI 预审报告卡片：数据来自 extra_data（ui_type = expense_pre_review） -->
              <div
                v-if="msg.role === 'ai' && preReviewView(msg.extraData)"
                class="claim-card pre-review-card"
              >
                <template v-for="report in asList(preReviewView(msg.extraData))" :key="`pr-${report.claim_no}`">
                  <div class="claim-card-head">
                    <span class="claim-card-title">
                      <el-icon><MagicStick /></el-icon>
                      {{ $t('chat.preReviewCardTitle') }}
                    </span>
                    <span class="claim-status" :class="claimStatusClass(report.status)">
                      {{ claimStatusLabel(report.status) }}
                    </span>
                  </div>

                  <!-- 单号 / 标题 / 金额 -->
                  <div class="cd-head pg-head">
                    <div class="pg-head-left">
                      <span class="cd-no">{{ report.claim_no }}</span>
                      <div class="cd-title">{{ report.title || $t('chat.claimUntitled') }}</div>
                    </div>
                    <div class="pg-head-amount">
                      {{ formatMoney(report.total_amount, report.currency) }}
                    </div>
                  </div>

                  <!-- 无预审记录 -->
                  <div v-if="!report.pre_review" class="cd-section">
                    <div class="cd-empty">{{ $t('chat.preReviewNoRecord') }}</div>
                  </div>

                  <!-- 预审进行中 -->
                  <div v-else-if="report.pre_review.status === 'running' || report.pre_review.status === 'pending'" class="cd-section">
                    <div class="cd-pr">
                      <div class="cd-pr-head">
                        <span class="claim-status" :class="claimPreReviewClass(report.pre_review)">
                          {{ claimPreReviewLabel(report.pre_review) }}
                        </span>
                      </div>
                      <div class="cd-tl-hint">{{ $t('chat.preReviewRunningHint') }}</div>
                    </div>
                  </div>

                  <!-- 预审执行失败 -->
                  <div v-else-if="report.pre_review.status === 'failed'" class="cd-section">
                    <div class="cd-pr">
                      <div class="cd-pr-head">
                        <span class="claim-status" :class="claimPreReviewClass(report.pre_review)">
                          {{ claimPreReviewLabel(report.pre_review) }}
                        </span>
                      </div>
                      <div v-if="report.pre_review.error_message" class="pr-evidence">
                        {{ report.pre_review.error_message }}
                      </div>
                    </div>
                  </div>

                  <!-- 预审完成：结论横幅 + 问题清单 + 依据 + 提取信息 -->
                  <template v-else>
                    <!-- 结论横幅 -->
                    <div class="pr-banner" :class="claimPreReviewClass(report.pre_review)">
                      <div class="pr-banner-head">
                        <span class="claim-status" :class="claimPreReviewClass(report.pre_review)">
                          {{ claimPreReviewLabel(report.pre_review) }}
                        </span>
                        <span
                          v-if="report.pre_review.risk_level"
                          class="claim-status"
                          :class="preReviewRiskClass(report.pre_review.risk_level)"
                        >
                          {{ preReviewRiskLabel(report.pre_review.risk_level) }}
                        </span>
                        <span v-if="preReviewDuration(report.pre_review)" class="pr-duration">
                          {{ $t('chat.preReviewDuration', { duration: preReviewDuration(report.pre_review) }) }}
                        </span>
                      </div>
                      <div v-if="report.pre_review.summary" class="pr-banner-summary">
                        {{ report.pre_review.summary }}
                      </div>
                    </div>

                    <!-- 发现的问题 -->
                    <div v-if="report.problems.length" class="cd-section">
                      <div class="cd-section-title">
                        {{ $t('chat.preReviewProblems') }}
                        <span class="cd-section-count">{{ report.problems.length }}</span>
                      </div>
                      <ul class="pr-problems">
                        <li v-for="(p, idx) in report.problems" :key="idx">
                          <el-icon><WarningFilled /></el-icon>
                          <span>{{ p }}</span>
                        </li>
                      </ul>
                    </div>

                    <!-- 判定依据 + 凭证核验 -->
                    <div v-if="report.pre_review.result_data?.evidence || report.pre_review.result_data?.is_document_valid != null" class="cd-section">
                      <div class="cd-section-title">{{ $t('chat.preReviewEvidence') }}</div>
                      <div v-if="report.pre_review.result_data?.evidence" class="pr-evidence">
                        {{ report.pre_review.result_data.evidence }}
                      </div>
                      <div
                        v-if="report.pre_review.result_data?.is_document_valid != null"
                        class="pr-doc"
                        :class="report.pre_review.result_data.is_document_valid ? 'pr-doc-ok' : 'pr-doc-bad'"
                      >
                        <el-icon>
                          <CircleCheck v-if="report.pre_review.result_data.is_document_valid" />
                          <CircleClose v-else />
                        </el-icon>
                        {{ report.pre_review.result_data.is_document_valid
                          ? $t('chat.preReviewDocValid')
                          : $t('chat.preReviewDocInvalid') }}
                      </div>
                    </div>

                    <!-- 提取的关键信息 -->
                    <div v-if="preReviewExtractedEntries(report.pre_review).length" class="cd-section">
                      <div class="cd-section-title">{{ $t('chat.preReviewExtracted') }}</div>
                      <div class="pr-extracted">
                        <div
                          v-for="entry in preReviewExtractedEntries(report.pre_review)"
                          :key="entry.label"
                          class="pr-extracted-row"
                        >
                          <span class="pr-extracted-label">{{ entry.label }}</span>
                          <span class="pr-extracted-value">{{ entry.value }}</span>
                        </div>
                      </div>
                    </div>
                  </template>
                </template>
              </div>

              <!-- 报销统计卡片：数据来自 extra_data（ui_type = expense_statistics） -->
              <div
                v-if="msg.role === 'ai' && statsList(msg.extraData).length"
                class="claim-card stats-card"
              >
                <template v-for="stats in statsList(msg.extraData)" :key="`st-${stats.date_from ?? 'all'}`">
                  <div class="claim-card-head">
                    <span class="claim-card-title">
                      <el-icon><TrendCharts /></el-icon>
                      {{ $t('chat.statsTitle') }}
                    </span>
                    <span v-if="stats.total != null" class="claim-card-count">
                      {{ $t('chat.statsCount', { count: stats.total }) }}
                    </span>
                  </div>

                  <!-- 统计区间 -->
                  <div v-if="stats.date_from || stats.date_to" class="cd-head">
                    <div class="cd-desc">
                      {{ formatClaimDate(stats.date_from) }} ~ {{ formatClaimDate(stats.date_to) }}
                    </div>
                  </div>

                  <!-- 金额总览（按币种） -->
                  <div class="st-overview">
                    <div
                      v-for="(cs, idx) in stats.currencies"
                      :key="`${cs.currency}-${idx}`"
                      class="st-amount-box"
                    >
                      <span class="st-amount-label">{{ $t('chat.statsTotalAmount') }}</span>
                      <span class="st-amount-value">
                        {{ formatMoney(cs.total_amount, cs.currency) }}
                      </span>
                      <span v-if="cs.claim_count != null" class="st-amount-sub">
                        {{ $t('chat.statsCount', { count: cs.claim_count }) }}
                        <template v-if="cs.average_amount != null">
                          · {{ $t('chat.statsAvgAmount') }} {{ formatMoney(cs.average_amount, cs.currency) }}
                        </template>
                      </span>
                    </div>
                  </div>

                  <!-- 状态分布：占比条 + 图例 -->
                  <div v-if="statsStatusSegments(stats.statusCounts).length" class="cd-section">
                    <div class="cd-section-title">{{ $t('chat.statsStatusDist') }}</div>
                    <div class="st-bar">
                      <span
                        v-for="seg in statsStatusSegments(stats.statusCounts)"
                        :key="seg.key"
                        class="st-bar-seg"
                        :class="seg.barClass"
                        :style="{ width: seg.pct + '%' }"
                      />
                    </div>
                    <div class="st-legend">
                      <span
                        v-for="seg in statsStatusSegments(stats.statusCounts)"
                        :key="seg.key"
                        class="st-legend-item"
                      >
                        <span class="st-legend-dot" :class="seg.barClass" />
                        {{ claimStatusLabel(seg.key) }}
                        <b>{{ seg.count }}</b>
                      </span>
                    </div>
                  </div>

                  <!-- 分类汇总：金额降序 + 比例条 -->
                  <div v-if="statsCategories(stats.categories).length" class="cd-section">
                    <div class="cd-section-title">
                      {{ $t('chat.statsByCategory') }}
                      <span class="cd-section-count">{{ statsCategories(stats.categories).length }}</span>
                    </div>
                    <div class="st-cats">
                      <div
                        v-for="cat in statsCategories(stats.categories)"
                        :key="`${cat.category}-${cat.currency}`"
                        class="st-cat"
                      >
                        <div class="st-cat-head">
                          <span class="st-cat-name">{{ cat.category || '-' }}</span>
                          <span class="st-cat-count">
                            {{ $t('chat.claimDetailItemsTotal', { count: cat.item_count ?? 0 }) }}
                          </span>
                          <span class="st-cat-amount">
                            {{ formatMoney(cat.total_amount, cat.currency) }}
                          </span>
                        </div>
                        <div class="st-cat-bar">
                          <span :style="{ width: cat.pct + '%' }" />
                        </div>
                      </div>
                    </div>
                  </div>
                </template>
              </div>
            </div>
            <div v-if="msg.role === 'ai'" class="msg-foot">
              <span>{{ msg.time }}</span>
              <template v-if="hasTokenUsage(msg)">
                <span class="msg-foot-sep">·</span>
                <span
                  class="msg-usage"
                  :title="$t('chat.tokenUsageHint')"
                >{{ $t('chat.tokenUsageLine', {
                  input: formatToken(msg.inputTokens),
                  output: formatToken(msg.outputTokens),
                  total: formatToken(msg.totalTokens)
                }) }}</span>
              </template>
            </div>
          </div>
        </div>

        <!-- 工作流实时进度：同一工作流的所有事件共用这一个区域，不插入多条 AI 消息 -->
        <div
          v-if="workflow && runProgressVisible"
          class="message-wrapper ai run-progress"
          :class="`run-${workflow.status}`"
        >
          <div class="message-avatar">
            <div class="avatar-badge ai">
              <el-icon v-if="hasActiveRun" class="is-loading"><Loading /></el-icon>
              <el-icon v-else-if="workflow.status === 'success'"><CircleCheck /></el-icon>
              <el-icon v-else><CircleClose /></el-icon>
            </div>
          </div>
          <div class="message-content-group">
            <div class="message-meta">
              <span class="message-author">{{ $t('chat.welcomeTitle') }}</span>
              <span class="llm-tag">{{ progressStatusLabel }}</span>
            </div>
            <div class="run-progress-box">
              <!-- 折叠开关：默认折叠只显示"正在执行…"；用户点开后，本次运行的进度气泡保持展开 -->
              <button
                class="run-collapse-btn"
                type="button"
                :title="runCollapsed ? $t('chat.runExpand') : $t('chat.runCollapse')"
                @click="toggleRunCollapse"
              >
                <el-icon>
                  <CaretBottom v-if="!runCollapsed" />
                  <CaretRight v-else />
                </el-icon>
              </button>
              <!-- 折叠态：失败展示错误，其余只显示 loading + "正在执行…" -->
              <template v-if="runCollapsed">
                <span v-if="workflow.errorMessage" class="run-progress-text error">{{ workflow.errorMessage }}</span>
                <template v-else>
                  <el-icon v-if="hasActiveRun" class="is-loading run-loading"><Loading /></el-icon>
                  <span class="run-progress-text">{{ $t('chat.runProgressCollapsed') }}</span>
                </template>
              </template>
              <!-- 展开态：完整进度信息 -->
              <template v-else>
                <span v-if="workflow.errorMessage" class="run-progress-text error">{{ workflow.errorMessage }}</span>
                <template v-else>
                  <!-- 与知识库文档上传进度一致的 loading -->
                  <el-icon v-if="hasActiveRun" class="is-loading run-loading"><Loading /></el-icon>
                  <span class="run-progress-text">
                    {{ workflow.connectionLost ? $t('chat.progressReconnecting') : (workflow.message || progressStatusLabel) }}
                  </span>
                  <span v-if="workflow.stepName && !workflow.connectionLost" class="run-step-name">· {{ workflow.stepName }}</span>
                </template>
              </template>
            </div>
            <div v-if="!runCollapsed && workflow.connectionLost" class="run-hint">{{ $t('chat.runConnectionLost') }}</div>
            <div v-else-if="!runCollapsed && isWaitingStatus(workflow.status)" class="run-hint">{{ $t('chat.runWaitingHint') }}</div>
          </div>
        </div>
      </div>

      <!-- （回到底部按钮已移入 chat-input-area，紧贴输入框上沿） -->

      <div class="chat-input-area">
        <!-- 用户向上翻阅历史时，提供一键回到底部；留在底部时自动跟随新消息。
             锚定在输入框容器上方（top 为负），移动端输入区被压缩后依然紧贴输入框 -->
        <transition name="fade">
          <button v-if="!isNearBottom" class="scroll-bottom-btn" @click="scrollToBottom(true)">
            <el-icon><Bottom /></el-icon> {{ $t('chat.scrollToBottom') }}
          </button>
        </transition>
        <div class="input-container">
          <el-input
            v-model="inputMsg"
            type="textarea"
            :rows="isMobileViewport ? 1 : 3"
            :placeholder="$t('chat.inputPlaceholder')"
            resize="none"
            class="custom-textarea"
            :autosize="isMobileViewport ? { minRows: 1, maxRows: 4 } : false"
            @keydown.enter.exact.prevent="handleSend"
          />
          <div class="input-toolbar">
            <button class="send-btn" @click="handleSend" :disabled="!inputMsg.trim() || loading || hasActiveRun">
              {{ $t('employee.send') }} <el-icon><Top /></el-icon>
            </button>
          </div>
        </div>
        <div class="input-disclaimer">{{ $t('chat.disclaimer') }}</div>
      </div>
    </div>

    <!-- 右侧：执行过程与信息 -->
    <aside class="execution-sidebar">
      <el-tabs v-model="activeTab" class="execution-tabs">
        <el-tab-pane :label="$t('chat.tabProcess')" name="process">
          <div class="process-status">
            <div class="status-badge" :class="{ failed: workflow?.status === 'failed', idle: !workflow }">
              <el-icon v-if="hasActiveRun" class="is-loading"><Loading /></el-icon>
              <el-icon v-else-if="workflow?.status === 'success'"><CircleCheck /></el-icon>
              <el-icon v-else-if="workflow"><CircleClose /></el-icon>
              <span>{{ workflow ? statusLabels[workflow.status] : $t('chat.notStarted') }}</span>
            </div>
            <div class="run-row"><span>Run ID</span><b>{{ workflow?.runUid || '-' }}</b></div>
            <div class="run-row"><span>{{ $t('chat.engine') }}</span><b>{{ runEngineLabel }}</b></div>
            <div class="run-row">
              <span>{{ $t('chat.latency') }}</span>
              <b :class="{ ok: !hasActiveRun }">{{ runDurationLabel }}</b>
            </div>
          </div>
          <div class="trace-title">{{ $t('chat.traceTitle') }}</div>
          <el-timeline class="custom-timeline">
            <el-timeline-item
              v-for="step in processSteps"
              :key="step.key"
              :type="step.type"
              :color="step.color"
              :hollow="step.hollow"
            >
              <div class="step-content">
                <div class="step-header">
                  <span class="step-title">
                    {{ step.title }}
                    <el-tag
                      v-if="step.state"
                      size="small"
                      effect="plain"
                      :type="stepStateMeta[step.state].type"
                      class="step-state-tag"
                    >{{ stepStateMeta[step.state].label }}</el-tag>
                  </span>
                  <span class="step-time">{{ step.time }}</span>
                </div>
                <div class="step-desc">{{ step.desc }}</div>
              </div>
            </el-timeline-item>
          </el-timeline>
          <div class="trace-title">{{ $t('chat.resourceTitle') }}</div>
          <div class="resource-grid">
          <div class="res-card">
            <span class="res-label">{{ $t('chat.tokenUsage') }}</span>
            <b class="res-value">{{ runTokenLabel }}</b>
            <span class="res-sub">{{ runTokenSubLabel }}</span>
          </div>
          <div class="res-card">
            <span class="res-label">{{ $t('chat.llmCalls') }}</span>
            <b class="res-value green">{{ runLlmCallsLabel }}</b>
            <span class="res-sub">{{ runRagLabel }}</span>
          </div>
          </div>
        </el-tab-pane>
        <el-tab-pane :label="$t('chat.tabTasks')" name="tasks">
          <div v-if="relatedTaskLoading" class="task-panel-loading">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>{{ $t('chat.tasksLoading') }}</span>
          </div>
          <div v-else-if="!relatedTasks.length" class="empty-state">{{ $t('chat.noRelatedTasks') }}</div>
          <div v-else class="task-panel-list">
            <button
              v-for="task in relatedTasks"
              :key="task.uid"
              type="button"
              class="task-panel-item"
              :class="{ active: task.uid === activeTaskUid }"
              @click="openRelatedTask(task)"
            >
              <div class="task-panel-head">
                <span class="task-panel-title">{{ task.title || $t('chat.taskDefaultTitle') }}</span>
                <span class="task-panel-status" :class="task.status">{{ taskStatusLabel(task.status) }}</span>
              </div>
              <div class="task-panel-meta">
                <span>{{ formatMoney(taskDisplayAmount(task)) }}</span>
                <span class="sep">·</span>
                <span>{{ $t('chat.taskPanelItemCount', { count: taskDisplayItemCount(task) }) }}</span>
                <template v-if="taskClaimNo(task)">
                  <span class="sep">·</span>
                  <span class="task-panel-claim">{{ taskClaimNo(task) }}</span>
                </template>
              </div>
              <div v-if="taskMissingLabels(task).length" class="task-panel-missing">
                {{ $t('chat.taskMissingPrefix') }}：{{ taskMissingLabels(task).join('、') }}
              </div>
            </button>
          </div>
        </el-tab-pane>
        <el-tab-pane :label="$t('chat.tabInfo')" name="info">
          <div class="info-list">
            <div class="info-item"><span class="label">{{ $t('chat.sessionId') }}</span><span class="value">{{ activeSession?.uid || '-' }}</span></div>
            <div class="info-item"><span class="label">{{ $t('chat.totalSessions') }}</span><span class="value">{{ totalConversations }}</span></div>
            <div class="info-item"><span class="label">{{ $t('chat.createdAt') }}</span><span class="value">{{ activeSession?.created_at ? new Date(activeSession.created_at).toLocaleString() : '-' }}</span></div>
            <div class="info-item"><span class="label">{{ $t('chat.updatedAt') }}</span><span class="value">{{ activeSession?.updated_at ? new Date(activeSession.updated_at).toLocaleString() : '-' }}</span></div>
            <div class="info-item"><span class="label">{{ $t('common.status') }}</span><el-tag size="small" :type="currentSessionId ? 'success' : 'info'">{{ currentSessionId ? $t('admin.stRunning') : $t('chat.notStarted') }}</el-tag></div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </aside>

    <!-- 移动端会话抽屉 -->
    <el-drawer v-model="sessionsDrawer" direction="ltr" size="78%" :with-header="false" class="af-sessions-drawer">
      <div class="drawer-sessions">
        <div class="sidebar-header">
          <span class="sidebar-title"><el-icon><ChatDotRound /></el-icon> {{ $t('chat.recentSessions') }}</span>
          <button class="new-chat-btn" @click="startNewChat(); sessionsDrawer = false"><el-icon><Plus /></el-icon></button>
        </div>
        <div class="session-search">
          <el-icon><Search /></el-icon>
          <input
            v-model="sessionKeyword"
            type="text"
            maxlength="50"
            :placeholder="$t('chat.searchSessions')"
            @keydown.esc="clearSearch"
          />
          <el-icon v-if="searching" class="is-loading search-spin"><Loading /></el-icon>
          <button
            v-else-if="isSearchMode"
            class="search-clear"
            type="button"
            :title="$t('chat.clearSearch')"
            :aria-label="$t('chat.clearSearch')"
            @click="clearSearch"
          >
            <el-icon><Close /></el-icon>
          </button>
        </div>
        <div v-if="isSearchMode && !searching && displaySessions.length" class="search-meta">
          <span>{{ $t('chat.searchResultCount', { count: searchTotal || displaySessions.length }) }}</span>
          <span v-if="searchTotal > displaySessions.length" class="search-meta-more">
            {{ $t('chat.searchResultLimited', { shown: displaySessions.length }) }}
          </span>
        </div>
        <div class="session-list">
          <div
            v-for="session in displaySessions"
            :key="session.uid"
            class="session-item"
            :class="{ active: currentSessionId === session.uid, editing: editingUid === session.uid }"
            @click="handleSelectSession(session.uid); sessionsDrawer = false"
          >
            <div v-if="editingUid === session.uid" class="session-rename" @click.stop>
              <input
                :ref="(el) => setRenameInput(el)"
                v-model="editingTitle"
                class="session-rename-input"
                type="text"
                maxlength="20"
                :placeholder="$t('chat.renamePlaceholder')"
                @keydown.enter.prevent="commitRename(session)"
                @keydown.esc.prevent="cancelRename"
                @blur="commitRename(session)"
              />
            </div>
            <template v-else>
              <div class="session-info">
                <div class="session-name" :title="session.name" @dblclick.stop="beginRename(session)">
                  <template v-for="(part, i) in highlightParts(session.name)" :key="i">
                    <mark v-if="part.match" class="session-hit">{{ part.text }}</mark>
                    <template v-else>{{ part.text }}</template>
                  </template>
                </div>
                <div class="session-preview">{{ session.time }}</div>
              </div>
              <div class="session-actions">
                <button
                  class="session-action-btn"
                  type="button"
                  :title="$t('chat.renameSession')"
                  :aria-label="$t('chat.renameSession')"
                  @click.stop="beginRename(session)"
                >
                  <el-icon><Edit /></el-icon>
                </button>
                <button
                  class="session-action-btn danger"
                  type="button"
                  :title="$t('chat.deleteSession')"
                  :aria-label="$t('chat.deleteSession')"
                  @click.stop="handleDeleteSession(session)"
                >
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
            </template>
          </div>
          <div v-if="sessions.length === 0 && !isSearchMode" class="session-empty-state">
            <div class="empty-illustration">
              <el-icon><ChatDotRound /></el-icon>
            </div>
            <p class="empty-title">{{ $t('chat.noSessionsTitle') }}</p>
            <p class="empty-desc">{{ $t('chat.noSessionsDesc') }}</p>
          </div>
          <div v-else-if="isSearchMode && searching && displaySessions.length === 0" class="session-empty">
            {{ $t('chat.searching') }}
          </div>
          <div v-else-if="isSearchMode && !searching && displaySessions.length === 0" class="session-empty">
            {{ $t('chat.noMatchSessions') }}
            <button class="empty-clear" type="button" @click="clearSearch">{{ $t('chat.clearSearch') }}</button>
          </div>
        </div>
        <!-- 抽屉底部：在线状态 + 今日额度（移动端顶栏不再显示在线状态） -->
        <div class="drawer-foot">
          <span class="drawer-online"><span class="dot green" /> {{ $t('chat.aiOnline') }}</span>
          <span>{{ $t('chat.quota') }} 4 / 50</span>
        </div>
      </div>
    </el-drawer>

    <!-- 删除会话确认弹窗（按设计语言还原的高危确认） -->
    <DeleteSessionDialog
      v-model="deleteDialogVisible"
      :session="deleteTarget"
      @confirm="onConfirmDeleteSession"
    />

    <!-- 报销单详情抽屉：点击聊天中的报销记录打开（只读，不含审批区） -->
    <PreReviewDrawer
      v-model="claimDrawerVisible"
      :claim-no="activeClaimNo"
      :claim-id="null"
      :title="$t('chat.claimDetailTitle')"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  Plus, ChatDotRound, Edit, Service, Paperclip,
  Document, Loading, Search, Top, Bottom, CircleCheck, CircleClose,
  CaretBottom, CaretRight, Delete, Close, Tickets, CopyDocument, WarningFilled, ArrowRight, Upload, Timer, Clock, MagicStick, TrendCharts
} from '@element-plus/icons-vue'
import {
  createConversationApi,
  sendMessageApi,
  getConversationsApi,
  getConversationMessagesApi,
  getConversationBusinessTasksApi,
  getWorkflowRunStatusApi,
  updateConversationTitleApi,
  deleteConversationApi,
  searchConversationsApi,
  uploadExpenseItemAttachmentApi,
  type ConversationResponse,
  type RunStepStatus,
  type RunMetrics,
  type WorkflowRunStatus,
  type ChatMessageExtraData,
  type BusinessTaskCardItem,
  type ExpenseClaimCardItem,
  type ExpenseClaimListPayload,
  type ExpenseClaimDetailPayload,
  type ExpenseClaimProgressPayload,
  type ExpenseClaimApprovalHistoryPayload,
  type ExpensePreReviewPayload,
  type ExpenseStatisticsPayload,
  type KnowledgeSourcesPayload,
  type KnowledgeSourceItem,
  type ExpenseItemDraft,
  type MessageSendOptions
} from '@/api/chat'
import { useWorkflowStream, isTerminalStatus } from '@/composables/useWorkflowStream'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import PreReviewDrawer from './expense/PreReviewDrawer.vue'
import DeleteSessionDialog from '@/components/DeleteSessionDialog.vue'
import { renderMarkdown } from '@/utils/markdown'
import { normalizeInvoiceFile, isSupportedInvoiceFile } from '@/utils/image'

const userStore = useUserStore()
const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const avatarText = computed(() => (userStore.userInfo?.nickname || userStore.userInfo?.username || 'U').slice(0, 1))

const currentSessionId = ref<string | null>(null)
const activeTab = ref('process')
const loading = ref(false)
const totalConversations = ref(0)
const sessionsDrawer = ref(false)
const sessionKeyword = ref('')

// 移动端视口：输入框行数等按屏幕宽度降级，避免占满小屏高度
const isMobileViewport = ref(false)
const viewportQuery = window.matchMedia('(max-width: 768px)')
const syncViewport = (e: MediaQueryList | MediaQueryListEvent) => { isMobileViewport.value = e.matches }
syncViewport(viewportQuery)
viewportQuery.addEventListener('change', syncViewport)
onBeforeUnmount(() => viewportQuery.removeEventListener('change', syncViewport))

// 草稿箱：切换会话时保留未发送的输入内容
const drafts = ref<Record<string, string>>({})
const draftKey = computed(() => String(currentSessionId.value ?? '__new__'))
// inputMsg：按会话维度的草稿代理
const inputMsg = computed({
  get: () => drafts.value[draftKey.value] ?? '',
  set: (v: string) => { drafts.value[draftKey.value] = v }
})

// 工作流相关本地缓存：同一次会话中保存未结束的 run，用于刷新后恢复
const LAST_CONVERSATION_KEY = 'chat:last-conversation'
const ACTIVE_RUN_PREFIX = 'chat:active-run:'

const saveActiveRun = (conversationUid: string, runUid: string) => {
  sessionStorage.setItem(ACTIVE_RUN_PREFIX + conversationUid, runUid)
}
const readActiveRun = (conversationUid: string): string | null =>
  sessionStorage.getItem(ACTIVE_RUN_PREFIX + conversationUid)
const clearActiveRun = (conversationUid: string) => {
  sessionStorage.removeItem(ACTIVE_RUN_PREFIX + conversationUid)
}

const nowTimeLabel = () =>
  new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

/** 把事件里的 ISO 时间格式化为本地时间，缺失或非法时回退到当前时间 */
const formatEventTime = (iso?: string): string => {
  if (!iso) return nowTimeLabel()
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return nowTimeLabel()
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/** 工作流状态文案 */
const statusLabels = computed<Record<WorkflowRunStatus, string>>(() => ({
  pending: t('chat.runStatusPending'),
  running: t('chat.runStatusRunning'),
  waiting_input: t('chat.runStatusWaitingInput'),
  waiting_confirmation: t('chat.runStatusWaitingConfirmation'),
  waiting_approval: t('chat.runStatusWaitingApproval'),
  success: t('chat.runStatusSuccess'),
  failed: t('chat.runStatusFailed'),
  cancelled: t('chat.runStatusCancelled')
}))

const WAITING_STATUSES: WorkflowRunStatus[] = ['waiting_input', 'waiting_confirmation', 'waiting_approval']
const isWaitingStatus = (status: WorkflowRunStatus) => WAITING_STATUSES.includes(status)

// 聊天区进度块的标签：排队瞬间显示"加载中"，其余状态用标准文案
const progressStatusLabel = computed(() => {
  const status = workflow.value?.status
  if (!status) return ''
  return status === 'pending' ? t('chat.loading') : statusLabels.value[status]
})

// 中间聊天区的工作流进度块是否展示（成功后收起，但右侧仍保留本次运行结果）
const runProgressVisible = ref(false)

// 进度气泡折叠状态：默认折叠，只显示 loading + "正在执行…"，点开后本次运行期间保持展开
const runCollapsed = ref(true)
const toggleRunCollapse = () => {
  runCollapsed.value = !runCollapsed.value
}

// SSE 生命周期统一由 composable 管理（断线先查状态、避免重复建连、卸载自动清理）
const { progress: workflow, start: startWorkflow, stop: stopWorkflow } = useWorkflowStream({
  onUpdate: (progress, event) => {
    // 旧会话的事件不得污染当前窗口
    if (progress.conversationUid !== currentSessionId.value) return

    const eventTime = formatEventTime(event.time)

    // run_started 不再生成"AI处理中"节点：中间步骤一律以 step_started 为准
    if (event.event === 'run_started') {
      // run_started 的 message 展示在"发送消息"节点下方
      updateProcessStep('run:sent', {
        desc: event.message || t('chat.stepSentDesc'),
        time: eventTime
      })
    } else if (event.event === 'step_started') {
      // 步骤开始执行时，确认"发送消息"已完成
      updateProcessStep('run:sent', { type: 'success', color: '#2ecc71', state: 'success' })
      // 按 step_key 聚合：同一步骤重复事件只更新节点，不新增
      // 展示名优先级：display_name > step_name > step_key
      const state: RunStepStatus =
        event.scope === 'step' && event.status ? (event.status as RunStepStatus) : 'running'
      upsertProcessStep(event.step_key || event.step_name || '__step', {
        title: event.display_name || event.step_name || t('chat.runStepStarted'),
        time: eventTime,
        desc: event.message || t('chat.stepThinking'),
        state,
        ...stepVisual(state)
      })
    } else if (event.event === 'progress') {
      // scope=step：更新当前步骤的说明与状态（状态取自 status 字段）
      // scope=run：仅更新整体进度文案，不动时间线节点
      const stepKey = event.step_key || event.step_name
      if (event.scope === 'step' && stepKey) {
        // progress 可能先于 step_started 到达（建连前已完成的步骤），这里按 step_key 补建节点
        const state: RunStepStatus = (event.status as RunStepStatus) || 'running'
        upsertProcessStep(stepKey, {
          title: event.display_name || event.step_name || stepKey,
          desc: event.message || '',
          time: eventTime,
          state,
          ...stepVisual(state)
        })
      }
    } else if (event.event === 'content_delta') {
      // 增量片段追加到同一条 assistant 消息，不新增气泡
      appendContentDelta(progress.runUid, event.delta)
      // 一旦开始输出正文，中间那条"执行中"进度气泡立刻收掉：
      // 否则它会和正在逐字显示的回答气泡并排成两条 AI 气泡（进度信息右侧时间线仍完整保留）
      runProgressVisible.value = false
    } else if (event.event === 'assistant_message') {
      // 最终完整内容 + Token 用量回填到同一条消息
      applyAssistantMessage(progress.runUid, {
        message_uid: event.message_uid,
        content: event.content,
        input_tokens: event.input_tokens ?? null,
        output_tokens: event.output_tokens ?? null,
        total_tokens: event.total_tokens ?? null,
        // 业务任务卡片随最终消息下发，必须一并合并，不能只更新文本
        extra_data: event.extra_data ?? null
      })
      // 后端可能不发/极少发 content_delta（如一次性返回整段内容），
      // 此时进度气泡会与回复气泡短暂并存成两条 AI 气泡：最终消息一到立刻收起
      runProgressVisible.value = false
    }
  },
  onTerminal: (progress) => {
    clearActiveRun(progress.conversationUid)
    // 本轮可能新增/更新了业务任务，终态时刷新右侧"相关任务"
    void loadRelatedTasks(progress.conversationUid)
    if (progress.conversationUid !== currentSessionId.value) return

    finalizeProcessSteps(progress.status)

    // 终态到达时回复可能还在逐字吐出：先标记终结，吐完再与服务器对齐，
    // 否则整段文字会在打字过程中被瞬间替换，视觉上"跳一下"。
    const stillTyping = messages.value.some(
      (m) => m.streaming && m.streamKey === progress.runUid
    )
    if (stillTyping) {
      messages.value = messages.value.map((m) =>
        m.streaming && m.streamKey === progress.runUid ? { ...m, streamDone: true } : m
      )
      deferredRefresh = {
        conversationUid: progress.conversationUid,
        runUid: progress.runUid,
        status: progress.status
      }
      scheduleTypingPump()
    }

    upsertProcessStep('run:end', {
      title:
        progress.status === 'success'
          ? t('chat.stepReplyDone')
          : progress.status === 'cancelled'
            ? t('chat.runCancelled')
            : t('chat.stepReplyFailed'),
      time: nowTimeLabel(),
      desc:
        progress.status === 'success'
          // 终态事件的 message 展示在结果节点下方（run_failed 时 error_message 优先于 message）
          ? progress.message || t('common.success')
          : progress.status === 'cancelled'
            ? progress.message || t('chat.runCancelled')
            : progress.errorMessage || progress.message || t('chat.runFailed'),
      type: progress.status === 'success' ? 'success' : 'danger',
      color: progress.status === 'success' ? '#2ecc71' : '#e74c3c',
      state: progress.status === 'success' ? 'success' : progress.status === 'cancelled' ? 'skipped' : 'failed'
    })

    // 以服务端消息为准刷新，保证最终回复不会重复或缺失；仍在吐字时交给 afterTypingDrained
    if (!stillTyping) {
      void fetchMessages(progress.conversationUid).then(() => {
        // 期间可能已切换会话或开始了新的运行，不能误清后者的进度
        if (progress.status === 'success' && workflow.value?.runUid === progress.runUid) {
          // 成功后只收起中间区域的进度块，右侧执行过程保留本次运行结果
          runProgressVisible.value = false
        }
      })
    }

    if (progress.status === 'failed') {
      ElMessage.error(progress.errorMessage || t('chat.runFailed'))
    } else if (progress.status === 'cancelled') {
      ElMessage.warning(t('chat.runCancelled'))
    }
  }
})

const hasActiveRun = computed(() => {
  const status = workflow.value?.status
  // 等待用户补充信息/确认/审批时需要允许继续发送，只有排队中和执行中才阻塞
  if (!status || (status !== 'pending' && status !== 'running')) return false
  // 连接已彻底中断时不再阻塞发送，避免用户无法继续操作
  return !workflow.value?.connectionLost
})

interface Session {
  uid: string
  name: string
  time: string
  created_at?: string
  updated_at?: string
}

const sessions = ref<Session[]>([])

// ===== 会话重命名 / 删除 =====
// 行内编辑同一时刻只允许一个会话
const editingUid = ref<string | null>(null)
const editingTitle = ref('')
const renaming = ref(false)
const deletingUid = ref<string | null>(null)
const renameInput = ref<HTMLInputElement | null>(null)

const setRenameInput = (el: unknown) => {
  renameInput.value = (el as HTMLInputElement) || null
}

/** 进入行内编辑并聚焦输入框（后端标题上限 20 字） */
const beginRename = async (session?: Session) => {
  if (!session?.uid) return
  editingUid.value = session.uid
  editingTitle.value = session.name
  await nextTick()
  renameInput.value?.focus()
  renameInput.value?.select()
}

const cancelRename = () => {
  editingUid.value = null
  editingTitle.value = ''
}

/** 提交标题修改：回车/失焦触发，Esc 取消；未改动时直接关闭 */
const commitRename = async (session: Session) => {
  if (editingUid.value !== session.uid || renaming.value) return
  const title = editingTitle.value.trim()
  if (!title || title === session.name) {
    cancelRename()
    return
  }
  renaming.value = true
  try {
    const res = await updateConversationTitleApi(session.uid, title)
    if (!(res.code === 0 || res.code === 200)) {
      throw new Error(res.msg || t('chat.renameFailed'))
    }
    // 以后端返回的标题为准（服务端会截断）
    const newTitle = res.data?.title || title.slice(0, 20)
    sessions.value = sessions.value.map((s) =>
      s.uid === session.uid ? { ...s, name: newTitle } : s
    )
    // 搜索结果里同一个会话也要同步，否则高亮还停留在旧标题上
    searchResults.value = searchResults.value.map((s) =>
      s.uid === session.uid ? { ...s, name: newTitle } : s
    )
    ElMessage.success(t('chat.renameSuccess'))
  } catch (error: any) {
    ElMessage.error(error?.message || t('chat.renameFailed'))
  } finally {
    renaming.value = false
    cancelRename()
  }
}

/** 顶栏标题旁的编辑图标：直接进入当前会话的重命名 */
const renameActiveSession = async () => {
  const session = activeSession.value
  if (!session) return
  // 窄屏下会话列表在抽屉里，先打开抽屉再聚焦
  if (window.innerWidth <= 900) sessionsDrawer.value = true
  await beginRename(session)
}

/** 删除会话：先弹高危确认框，确认后再走真实删除 */
const deleteDialogVisible = ref(false)
const deleteTarget = ref<Session | null>(null)
const handleDeleteSession = (session: Session) => {
  if (!session?.uid || deletingUid.value) return
  deleteTarget.value = session
  deleteDialogVisible.value = true
}
const onConfirmDeleteSession = () => {
  const session = deleteTarget.value
  deleteTarget.value = null
  if (session) void performDeleteSession(session)
}

const performDeleteSession = async (session: Session) => {
  if (!session?.uid || deletingUid.value) return
  try {
    deletingUid.value = session.uid
    const res = await deleteConversationApi(session.uid)
    if (!(res.code === 0 || res.code === 200)) {
      throw new Error(res.msg || t('chat.deleteFailed'))
    }
    const wasCurrent = currentSessionId.value === session.uid
    sessions.value = sessions.value.filter((s) => s.uid !== session.uid)
    totalConversations.value = Math.max(0, totalConversations.value - 1)
    // 搜索结果与本地列表是两套数据，删掉后同步移除，避免列表里还挂着已删除的会话
    if (isSearchMode.value) {
      searchResults.value = searchResults.value.filter((s) => s.uid !== session.uid)
      searchTotal.value = Math.max(0, searchTotal.value - 1)
      // 会话已清空时退出搜索态，让空引导重新出现
      if (totalConversations.value === 0) clearSearch()
    }
    if (editingUid.value === session.uid) cancelRename()

    if (wasCurrent) {
      // 清缓存 + 停止订阅 + 清空聊天区，再切到剩余会话（没有则回到初始空态）
      clearActiveRun(session.uid)
      startNewChat()
      const next = sessions.value[0]
      if (next) {
        await handleSelectSession(next.uid)
      } else {
        sessionsDrawer.value = false
      }
    }
    ElMessage.success(t('chat.deleted'))
  } catch (error: any) {
    ElMessage.error(error?.message || t('chat.deleteFailed'))
  } finally {
    deletingUid.value = null
  }
}

// ===== 历史会话搜索（服务端按标题模糊匹配，替代原先的本地过滤） =====
const SEARCH_DEBOUNCE = 300
const SEARCH_PAGE_SIZE = 50
const searchResults = ref<Session[]>([])
const searchTotal = ref(0)
const searching = ref(false)
// 递增序号用于丢弃过期响应：用户连续输入时只认最后一次请求
let searchSeq = 0
let searchTimer: ReturnType<typeof setTimeout> | null = null

const isSearchMode = computed(() => sessionKeyword.value.trim().length > 0)
// 搜索态展示服务端结果，否则展示本地会话列表
const displaySessions = computed(() => (isSearchMode.value ? searchResults.value : sessions.value))

/** 后端会话记录 → 侧栏展示项（列表与搜索结果共用同一映射） */
const toSession = (item: ConversationResponse): Session => ({
  uid: item.uid,
  name: item.title,
  time: new Date(item.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  created_at: item.created_at,
  updated_at: item.updated_at
})

/** 清空搜索态并让所有在途请求失效 */
const resetSearch = () => {
  if (searchTimer) { clearTimeout(searchTimer); searchTimer = null }
  searchSeq++
  searchResults.value = []
  searchTotal.value = 0
  searching.value = false
}

const clearSearch = () => {
  sessionKeyword.value = ''
  resetSearch()
}

const runSearch = async (keyword: string) => {
  const seq = ++searchSeq
  searching.value = true
  try {
    const res = await searchConversationsApi(keyword, 1, SEARCH_PAGE_SIZE)
    if (seq !== searchSeq) return
    if (!(res.code === 0 || res.code === 200)) {
      throw new Error(res.msg || t('chat.searchFailed'))
    }
    searchResults.value = res.data.items.map(toSession)
    searchTotal.value = res.data.total
  } catch {
    if (seq !== searchSeq) return
    // 错误提示由统一请求拦截器给出，这里只保证不残留上一个关键词的结果
    searchResults.value = []
    searchTotal.value = 0
  } finally {
    if (seq === searchSeq) searching.value = false
  }
}

// 输入防抖：停顿 300ms 才发请求；清空关键词立即回到本地列表
watch(sessionKeyword, (val) => {
  if (searchTimer) { clearTimeout(searchTimer); searchTimer = null }
  const keyword = val.trim()
  if (!keyword) {
    resetSearch()
    return
  }
  searching.value = true
  searchTimer = setTimeout(() => {
    searchTimer = null
    void runSearch(keyword)
  }, SEARCH_DEBOUNCE)
})

/** 把会话标题按关键词切片，用于搜索结果高亮（后端是 ilike，忽略大小写） */
const highlightParts = (text: string): { text: string; match: boolean }[] => {
  const keyword = sessionKeyword.value.trim()
  if (!keyword || !text) return [{ text, match: false }]
  const lowerText = text.toLowerCase()
  const lowerKeyword = keyword.toLowerCase()
  const parts: { text: string; match: boolean }[] = []
  let cursor = 0
  let hit = lowerText.indexOf(lowerKeyword)
  while (hit >= 0) {
    if (hit > cursor) parts.push({ text: text.slice(cursor, hit), match: false })
    parts.push({ text: text.slice(hit, hit + keyword.length), match: true })
    cursor = hit + keyword.length
    hit = lowerText.indexOf(lowerKeyword, cursor)
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), match: false })
  return parts.length ? parts : [{ text, match: false }]
}

// 搜索结果里的会话可能不在本地列表（后端列表按页返回），因此两处都要查
const activeSession = computed(
  () =>
    sessions.value.find((s) => s.uid === currentSessionId.value) ||
    searchResults.value.find((s) => s.uid === currentSessionId.value)
)

interface Message {
  uid?: string
  role: 'user' | 'ai' | 'assistant'
  time: string
  type: 'text' | 'table' | 'detail-card'
  content?: string
  tableTitle?: string
  tableData?: any[]
  columns?: { prop: string; label: string }[]
  tableFooter?: string
  cardTitle?: string
  details?: {
    applicant: string
    type: string
    dateRange: string
    attachments: string
    location: string
    applyTime: string
    amount: string
    approver: string
  }
  actions?: string[]
  /** Token 用量（仅 assistant 消息，后端未统计时为 null） */
  inputTokens?: number | null
  outputTokens?: number | null
  totalTokens?: number | null
  /** 业务卡片数据（仅 assistant 消息，来自后端 extra_data，原样保留不丢弃） */
  extraData?: ChatMessageExtraData
  /** 是否仍在增量接收中（用于展示光标） */
  streaming?: boolean
  /** 增量阶段的归属键（run_uid），收到 assistant_message 后仍保留以便回填 */
  streamKey?: string
  /**
   * 已收到但尚未"打字"显示完的完整文本。
   * 后端可能把整段内容在几十毫秒内一次性推完，靠它把渲染节奏交给前端逐字吐出。
   */
  streamTarget?: string
  /** 后端已确认最终内容（assistant_message 已到达），吐字完成后即可收尾 */
  streamDone?: boolean
}

const messages = ref<Message[]>([])

/** 空会话引导：点击建议直接发送（走与输入框一致的统一发送流程）。
 * 管理员视角没有"我的报销"，第二条建议去掉"我"字。 */
const welcomeSuggestions = computed<string[]>(() => {
  const isAdmin = userStore.userInfo?.role === 'admin'
  return [
    t('chat.suggestion1'),
    isAdmin ? t('chat.suggestion2Admin') : t('chat.suggestion2'),
    t('chat.suggestion3'),
  ]
})

// ===== 聊天区滚动 =====
const messageScroll = ref<HTMLElement | null>(null)
// 是否停留在底部附近：为 true 时新消息/进度更新自动跟随，否则不打断用户翻阅历史
const isNearBottom = ref(true)
const NEAR_BOTTOM_THRESHOLD = 80
// 程序化滚动的保护窗口，避免平滑滚动过程中的中间位置被误判为"已离开底部"
let autoScrollUntil = 0

const updateNearBottom = () => {
  if (Date.now() < autoScrollUntil) return
  const el = messageScroll.value
  if (!el) return
  isNearBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_THRESHOLD
}

/** 滚动到聊天底部；smooth 为 false 时用于会话切换等瞬间定位 */
const scrollToBottom = async (smooth = true) => {
  await nextTick()
  const el = messageScroll.value
  if (!el) return
  autoScrollUntil = Date.now() + (smooth ? 700 : 120)
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  isNearBottom.value = true
}

// 新消息、AI 回复、工作流进度变化时自动跟随到底部
watch(
  () => [messages.value.length, workflow.value?.status, workflow.value?.message, runProgressVisible.value],
  () => {
    if (isNearBottom.value) void scrollToBottom()
  }
)

// 进度连接中断时，增量大概率已经丢失：先收掉光标、把已收到的文字吐完，
// 避免光标无限闪烁；连接恢复或拿到终态后会对齐服务端最终内容。
watch(
  () => workflow.value?.connectionLost,
  (lost) => {
    if (!lost) return
    if (messages.value.some((m) => m.streaming)) {
      messages.value = messages.value.map((m) =>
        m.streaming ? { ...m, streamDone: true } : m
      )
      scheduleTypingPump()
    }
  }
)

// 需要用户补充信息/确认/审批时，正文气泡不足以表达，重新展示进度气泡并给出提示
watch(
  () => workflow.value?.status,
  (status) => {
    if (status && isWaitingStatus(status)) runProgressVisible.value = true
  }
)

// 高频增量事件用 rAF 合并滚动，避免每个 delta 都排队一次滚动动画
let scrollFrame = 0
const scheduleScroll = () => {
  if (!isNearBottom.value || scrollFrame) return
  scrollFrame = requestAnimationFrame(() => {
    scrollFrame = 0
    void scrollToBottom(false)
  })
}

interface ProcessStep {
  /** 节点唯一标识：step_key / run:started / run:end 等，用于合并更新 */
  key: string
  title: string
  time: string
  desc: string
  type?: string
  color?: string
  hollow?: boolean
  /** 步骤状态（来自 scope=step 的事件），与工作流状态分开维护 */
  state?: RunStepStatus
}

/** 步骤状态对应的标签样式与文案 */
const stepStateMeta = computed<Record<RunStepStatus, { label: string; type: 'info' | 'primary' | 'success' | 'danger' }>>(() => ({
  pending: { label: t('chat.stepStatePending'), type: 'info' },
  running: { label: t('chat.stepStateRunning'), type: 'primary' },
  success: { label: t('chat.stepStateSuccess'), type: 'success' },
  failed: { label: t('chat.stepStateFailed'), type: 'danger' },
  skipped: { label: t('chat.stepStateSkipped'), type: 'info' }
}))

// 执行过程时间线（无运行记录时的占位节点）
const processSteps = ref<ProcessStep[]>([
  { key: 'idle', title: t('chat.stepReceive'), time: '-', desc: t('chat.waitingInput'), type: 'info', hollow: true },
])

// 按 key 新增或更新步骤：同一步骤的重复事件只更新原节点
const upsertProcessStep = (key: string, step: Omit<ProcessStep, 'key'>) => {
  const index = processSteps.value.findIndex((item) => item.key === key)
  if (index >= 0) {
    const next = [...processSteps.value]
    next[index] = { ...next[index], ...step }
    processSteps.value = next
    return
  }
  processSteps.value = [...processSteps.value.filter((item) => item.key !== 'idle'), { key, ...step }]
}

// 仅更新已有步骤的描述信息（progress 事件）
const updateProcessStep = (key: string, patch: Partial<Omit<ProcessStep, 'key'>>) => {
  const index = processSteps.value.findIndex((item) => item.key === key)
  if (index < 0) return
  const next = [...processSteps.value]
  next[index] = { ...next[index], ...patch }
  processSteps.value = next
}

/** 步骤状态 → 时间线节点配色 */
const stepVisual = (state: RunStepStatus): { type: string; color: string } => {
  switch (state) {
    case 'success':
      return { type: 'success', color: '#2ecc71' }
    case 'failed':
      return { type: 'danger', color: '#e74c3c' }
    case 'skipped':
      return { type: 'info', color: '#909399' }
    case 'pending':
      return { type: 'info', color: '#909399' }
    default:
      return { type: 'primary', color: '#ff5c33' }
  }
}

// 工作流进入终态时收敛仍在执行中的步骤节点，避免时间线一直显示进行中
const finalizeProcessSteps = (status: WorkflowRunStatus) => {
  const isSuccess = status === 'success'
  const isCancelled = status === 'cancelled'
  const nextState: RunStepStatus = isSuccess ? 'success' : isCancelled ? 'skipped' : 'failed'
  processSteps.value = processSteps.value.map((step) =>
    step.state === 'running' || step.state === 'pending'
      ? { ...step, state: nextState, ...stepVisual(nextState) }
      : step
  )
}

/** 增量消息的临时 uid 前缀（收到 assistant_message 后会被真实 message_uid 替换） */
const STREAM_UID_PREFIX = 'stream:'

// ===== 打字机（typewriter）=====
// 后端一个 content_delta 可能把整段回复在几十毫秒内推完（实测十几次增量集中在 30ms 内），
// 若收到就渲染，用户只会看到整段文字"瞬间出现"。因此把渲染节奏交给前端：
// 收到的文本先进入 streamTarget，每帧取出若干字符写入 content，形成逐字效果。
// 积压越多单帧取字越多，既能保持逐字感，又不会明显落后于后端。
const TYPE_TICK_MS = 16
/** 积压文本按该系数分摊到每帧（约 60 帧/秒吐完一段 150 字回复≈1.9s，接近真人语速） */
const TYPE_BACKLOG_DIVISOR = 24

let typingTimer: ReturnType<typeof setTimeout> | null = null
/** 终态已到但仍在吐字：等吐完再做服务端对齐刷新，避免文字被瞬间替换 */
let deferredRefresh: { conversationUid: string; runUid: string; status: WorkflowRunStatus } | null = null

const stopTypingPump = () => {
  if (typingTimer !== null) {
    clearTimeout(typingTimer)
    typingTimer = null
  }
}

const scheduleTypingPump = () => {
  if (typingTimer !== null) return
  typingTimer = setTimeout(stepTyping, TYPE_TICK_MS)
}

/** 一次吐字：为每条仍在流式输出的消息补上若干个字符 */
const stepTyping = () => {
  typingTimer = null
  const list = messages.value
  let backlogLeft = false
  let drained = false

  for (let i = 0; i < list.length; i++) {
    const msg = list[i]
    if (!msg.streaming) continue
    const target = msg.streamTarget ?? ''
    const shown = msg.content?.length ?? 0

    if (shown < target.length) {
      const backlog = target.length - shown
      const step = Math.max(1, Math.ceil(backlog / TYPE_BACKLOG_DIVISOR))
      list[i] = { ...msg, content: target.slice(0, shown + step) }
      backlogLeft = true
    } else if (msg.streamDone) {
      // 内容已吐完且后端确认终结，收掉光标
      list[i] = { ...msg, streaming: false, streamDone: false }
      drained = true
    }
  }

  scheduleScroll()
  if (backlogLeft) {
    scheduleTypingPump()
  } else if (drained) {
    void afterTypingDrained()
  }
}

/** 吐字结束后再与服务端对齐，避免最终内容把正在逐字显示的文字"瞬间替换" */
const afterTypingDrained = async () => {
  const pending = deferredRefresh
  if (!pending) return
  deferredRefresh = null
  // 失败/取消没有最终消息可对齐，保留已经展示的部分内容
  if (pending.status !== 'success') return
  // 用户恰好在吐字结束前又发了一条消息：整体替换会冲掉这条乐观消息，跳过对齐
  if (loading.value || messages.value.some((m) => !m.uid)) return
  await fetchMessages(pending.conversationUid)
  if (workflow.value?.runUid === pending.runUid) runProgressVisible.value = false
}

/**
 * content_delta：把增量片段累积到本次运行的 assistant 消息。
 * 第一个片段到达时创建一条消息，之后的片段只扩展 streamTarget，
 * 实际显示交给打字机逐字吐出，不会为每个片段创建独立气泡。
 */
const appendContentDelta = (runUid: string, delta?: string | null) => {
  if (!delta) return

  const index = messages.value.findIndex((m) => m.role === 'ai' && m.streamKey === runUid)
  if (index >= 0) {
    const current = messages.value[index]
    messages.value[index] = {
      ...current,
      streamTarget: `${current.streamTarget ?? current.content ?? ''}${delta}`
    }
  } else {
    messages.value.push({
      uid: `${STREAM_UID_PREFIX}${runUid}`,
      role: 'ai',
      time: nowTimeLabel(),
      type: 'text',
      content: '',
      streamTarget: delta,
      streaming: true,
      streamKey: runUid
    })
  }
  scheduleTypingPump()
  scheduleScroll()
}

/**
 * assistant_message：用最终完整内容确认/回填同一条 assistant 消息。
 * 优先按 message_uid 匹配；没有则按本次 run 的增量占位消息匹配。
 * 最终内容只写入 streamTarget，由打字机继续吐完，不会直接覆盖屏幕上的文字。
 */
const applyAssistantMessage = (
  runUid: string,
  payload: {
    message_uid?: string
    content?: string
    input_tokens?: number | null
    output_tokens?: number | null
    total_tokens?: number | null
    extra_data?: ChatMessageExtraData
  }
) => {
  let index = payload.message_uid
    ? messages.value.findIndex((m) => m.uid === payload.message_uid)
    : -1
  if (index < 0) {
    index = messages.value.findIndex((m) => m.role === 'ai' && m.streamKey === runUid)
  }

  const tokenPatch = {
    inputTokens: payload.input_tokens ?? null,
    outputTokens: payload.output_tokens ?? null,
    totalTokens: payload.total_tokens ?? null
  }

  if (index >= 0) {
    const current = messages.value[index]
    const displayed = current.content ?? ''
    const target = payload.content ?? current.streamTarget ?? displayed
    // 极端情况（增量丢失）下最终内容与已显示内容不一致时，从头重新吐字，避免文本错乱
    const keepPrefix = target.startsWith(displayed)
    messages.value[index] = {
      ...current,
      uid: payload.message_uid || current.uid,
      content: keepPrefix ? displayed : '',
      streamTarget: target,
      streaming: true,
      streamDone: true,
      streamKey: current.streamKey ?? runUid,
      ...tokenPatch,
      // 本次没下发卡片时保留原值，避免多次推送把卡片冲掉
      extraData: payload.extra_data ?? current.extraData ?? null
    }
    scheduleTypingPump()
    return
  }

  if (!payload.content && !payload.extra_data) return
  messages.value.push({
    uid: payload.message_uid,
    role: 'ai',
    time: nowTimeLabel(),
    type: 'text',
    content: '',
    streamTarget: payload.content ?? '',
    streaming: true,
    streamDone: true,
    streamKey: runUid,
    ...tokenPatch,
    extraData: payload.extra_data ?? null
  })
  scheduleTypingPump()
}

/** 是否具备可展示的 Token 用量（后端未统计时不展示） */
const hasTokenUsage = (msg: Message) =>
  msg.role === 'ai' &&
  [msg.inputTokens, msg.outputTokens, msg.totalTokens].some(
    (value) => typeof value === 'number' && Number.isFinite(value)
  )

// ===== 知识库引用来源卡片（extra_data.ui_type = knowledge_sources） =====
interface KnowledgeSourceGroup {
  title: string
  kbName: string | null
  items: KnowledgeSourceItem[]
}
/** 按文档标题分组（保持接口返回顺序），空数据/未知结构返回空数组 */
const knowledgeSourceGroups = (extra?: ChatMessageExtraData): KnowledgeSourceGroup[] => {
  if (!extra || typeof extra !== 'object') return []
  const payload = extra as KnowledgeSourcesPayload
  if (payload.ui_type !== 'knowledge_sources') return []
  const list = Array.isArray(payload.knowledge_sources) ? payload.knowledge_sources : []
  const groups: KnowledgeSourceGroup[] = []
  for (const src of list) {
    const title = (src.document_title || '').trim() || '未知文档'
    let group = groups.find((g) => g.title === title)
    if (!group) {
      group = { title, kbName: (src.knowledge_base_name || '').trim() || null, items: [] }
      groups.push(group)
    }
    group.items.push(src)
  }
  return groups
}
/** 引用来源分组折叠状态：默认折叠，key = 消息下标 + 文档标题 */
const expandedKsKeys = ref(new Set<string>())
const ksGroupKey = (msg: Message, title: string) => `${messages.value.indexOf(msg)}-${title}`
const isKsExpanded = (msg: Message, title: string) => expandedKsKeys.value.has(ksGroupKey(msg, title))
const toggleKsGroup = (msg: Message, title: string) => {
  const next = new Set(expandedKsKeys.value)
  const key = ksGroupKey(msg, title)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedKsKeys.value = next
}

/** 引用条目能否跳转：必须同时有文档 uid 和知识库 uid（历史数据缺字段时保持只读） */
const canJumpSource = (src: KnowledgeSourceItem) => !!src.document_uid && !!src.knowledge_base_uid

/** 点击引用条目 → 打开文档预览，并把锚点带过去定位命中段落 */
const jumpToSource = (src: KnowledgeSourceItem) => {
  if (!canJumpSource(src)) return
  void router.push({
    name: 'CitationDocument',
    params: {
      kbId: src.knowledge_base_uid as string,
      docId: src.document_uid as string,
    },
    query: {
      anchor: (src.anchor_text || '').slice(0, 60),
      loc: src.location || '',
    },
  })
}

/** 包装为数组供模板 v-for 取非空类型（空数组 falsy 场景处理） */
const knowledgeSourceGroupsList = (extra?: ChatMessageExtraData): KnowledgeSourceGroup[][] => {
  const groups = knowledgeSourceGroups(extra)
  return groups.length ? [groups] : []
}

// ===== 业务任务卡片（extra_data.ui_type 协议） =====
// 卡片数据只从 extra_data 读取，绝不解析 AI 回复文本；未知类型/异常结构一律忽略，不影响文本渲染
const taskListOf = (extra?: ChatMessageExtraData): BusinessTaskCardItem[] => {
  if (!extra || typeof extra !== 'object') return []
  const payload = extra as { ui_type?: string; business_tasks?: unknown }
  if (payload.ui_type !== 'business_task_list' || !Array.isArray(payload.business_tasks)) return []
  return payload.business_tasks.filter(
    (task): task is BusinessTaskCardItem =>
      !!task && typeof task === 'object' && typeof (task as BusinessTaskCardItem).uid === 'string'
  )
}

const taskOf = (extra?: ChatMessageExtraData): BusinessTaskCardItem | null => {
  if (!extra || typeof extra !== 'object') return null
  const payload = extra as { ui_type?: string; business_task?: unknown }
  if (payload.ui_type !== 'business_task' || !payload.business_task) return null
  const task = payload.business_task as BusinessTaskCardItem
  return typeof task.uid === 'string' ? task : null
}

/** 任务状态文案：已知状态取 i18n，未知状态原样展示，避免留空 */
const TASK_STATUS_KEYS: Record<string, string> = {
  collecting: 'chat.taskStatusCollecting',
  waiting_input: 'chat.taskStatusWaitingInput',
  waiting_confirmation: 'chat.taskStatusWaitingConfirmation',
  waiting_approval: 'chat.taskStatusWaitingApproval',
  submitted: 'chat.taskStatusSubmitted',
  completed: 'chat.taskStatusCompleted',
  cancelled: 'chat.taskStatusCancelled'
}
const taskStatusLabel = (status?: string) => {
  if (!status) return ''
  const key = TASK_STATUS_KEYS[status]
  return key ? t(key) : status
}

/** 正式报销单状态（claim_status）与任务状态是两个维度，单独映射 */
const CLAIM_STATUS_KEYS: Record<string, string> = {
  draft: 'chat.claimStatusDraft',
  pending_approval: 'chat.claimStatusPendingApproval',
  needs_info: 'chat.claimStatusNeedsInfo',
  approved: 'chat.claimStatusApproved',
  rejected: 'chat.claimStatusRejected',
  processing: 'chat.claimStatusProcessing',
  completed: 'chat.claimStatusCompleted',
  failed: 'chat.claimStatusFailed'
}
const claimStatusLabel = (status?: string | null) => {
  if (!status) return ''
  const key = CLAIM_STATUS_KEYS[status]
  return key ? t(key) : status
}

// ===== 报销记录列表卡片（extra_data.ui_type = expense_claim_list） =====
// 只认结构化卡片数据，没有 ui_payload / 类型不符时照旧按文本消息渲染
const claimPayloadOf = (extra?: ChatMessageExtraData): ExpenseClaimListPayload | null => {
  if (!extra || typeof extra !== 'object') return null
  const payload = extra as { ui_type?: string; expense_claims?: unknown }
  if (payload.ui_type !== 'expense_claim_list' || !Array.isArray(payload.expense_claims)) return null
  return extra as ExpenseClaimListPayload
}

const claimRowsOf = (extra?: ChatMessageExtraData): ExpenseClaimCardItem[] => {
  const payload = claimPayloadOf(extra)
  if (!payload) return []
  return payload.expense_claims.filter(
    (claim): claim is ExpenseClaimCardItem =>
      !!claim && typeof claim === 'object' && typeof claim.claim_no === 'string'
  )
}

/** 分页视图：字段缺失时按条数兜底，避免出现 0 页 */
const claimPagerOf = (extra?: ChatMessageExtraData) => {
  const payload = claimPayloadOf(extra)
  const rows = claimRowsOf(extra)
  const pg = payload?.pagination
  const total = Number(pg?.total ?? rows.length) || 0
  const pageSize = Number(pg?.page_size ?? (rows.length || 20)) || 20
  const page = Math.max(Number(pg?.page ?? 1) || 1, 1)
  const computedPages = pageSize > 0 ? Math.ceil(total / pageSize) : 0
  const totalPages = Math.max(Number(pg?.total_pages ?? computedPages) || computedPages, total > 0 ? 1 : 0)
  return { total, page, totalPages }
}

/** 状态配色：待审批橙 / 已通过·已完成绿 / 已驳回红 / 草稿灰 / 处理中蓝 */
const CLAIM_STATUS_CLASS: Record<string, string> = {
  pending_approval: 'st-pending',
  needs_info: 'st-pending',
  approved: 'st-ok',
  completed: 'st-ok',
  rejected: 'st-fail',
  failed: 'st-fail',
  processing: 'st-processing',
  draft: 'st-draft'
}
const claimStatusClass = (status?: string | null) => CLAIM_STATUS_CLASS[status ?? ''] ?? 'st-draft'

/** 申请时间：ISO → 本地 YYYY-MM-DD HH:mm */
const formatClaimTime = (value?: string | null): string => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

// ===== 报销单详情卡片（extra_data.ui_type = expense_claim_detail） =====
const claimDetailOf = (extra?: ChatMessageExtraData): ExpenseClaimDetailPayload | null => {
  if (!extra || typeof extra !== 'object') return null
  const payload = extra as { ui_type?: string; expense_claim?: unknown }
  if (
    payload.ui_type !== 'expense_claim_detail' ||
    !payload.expense_claim ||
    typeof payload.expense_claim !== 'object' ||
    typeof (payload.expense_claim as { claim_no?: unknown }).claim_no !== 'string'
  ) {
    return null
  }
  return extra as ExpenseClaimDetailPayload
}

/** AI 预审结果 → 文案与配色 class（入参为 pre_review 对象，详情/预审卡片共用） */
const PRE_REVIEW_LABEL_KEYS: Record<string, string> = {
  pass: 'chat.preReviewPass',
  fail: 'chat.preReviewFail',
  manual: 'chat.preReviewManual'
}
const claimPreReviewLabel = (pr?: ExpenseClaimCardItem['pre_review']) => {
  if (!pr) return ''
  if (pr.result && PRE_REVIEW_LABEL_KEYS[pr.result]) return t(PRE_REVIEW_LABEL_KEYS[pr.result])
  if (pr.status === 'running' || pr.status === 'pending') return t('chat.preReviewRunning')
  if (pr.status === 'failed') return t('chat.preReviewFailed')
  return ''
}
const claimPreReviewClass = (pr?: ExpenseClaimCardItem['pre_review']) => {
  if (!pr) return ''
  if (pr.result === 'pass') return 'st-ok'
  if (pr.result === 'fail') return 'st-fail'
  if (pr.result === 'manual') return 'st-pending'
  return 'st-draft'
}

/** 风险等级 → 文案与配色 class */
const RISK_LABEL_KEYS: Record<string, string> = {
  high: 'chat.riskHigh',
  medium: 'chat.riskMedium',
  low: 'chat.riskLow'
}
const preReviewRiskLabel = (level?: string | null) => {
  const key = RISK_LABEL_KEYS[level ?? '']
  return key ? t(key) : level || ''
}
const preReviewRiskClass = (level?: string | null) =>
  level === 'high' ? 'st-fail' : level === 'medium' ? 'st-pending' : level === 'low' ? 'st-ok' : 'st-draft'

/** 预审耗时：finished_at - started_at → 「x.xs」 */
const preReviewDuration = (pr?: ExpenseClaimCardItem['pre_review']) => {
  if (!pr?.started_at || !pr.finished_at) return null
  const ms = new Date(pr.finished_at).getTime() - new Date(pr.started_at).getTime()
  if (!Number.isFinite(ms) || ms < 0) return null
  return `${(ms / 1000).toFixed(1)}s`
}

/** 提取的关键信息：过滤空值 + 已知字段翻译 */
const EXTRACTED_LABEL_KEYS: Record<string, string> = {
  invoice_no: 'chat.extractInvoiceNo',
  invoice_date: 'chat.extractInvoiceDate',
  total_amount: 'chat.extractAmount',
  seller_name: 'chat.extractSeller',
  buyer_name: 'chat.extractBuyer',
  tax_rate: 'chat.extractTaxRate',
  tax_amount: 'chat.extractTaxAmount'
}
const preReviewExtractedEntries = (pr?: ExpenseClaimCardItem['pre_review']) => {
  const data = pr?.result_data?.extracted_data
  if (!data || typeof data !== 'object') return []
  return Object.entries(data as Record<string, unknown>)
    .filter(([, v]) => v !== null && v !== undefined && v !== '' && !(typeof v === 'object' && !Array.isArray(v) && Object.keys(v as object).length === 0))
    .map(([k, v]) => ({
      label: EXTRACTED_LABEL_KEYS[k] ? t(EXTRACTED_LABEL_KEYS[k]) : k,
      value: Array.isArray(v) ? v.join('，') : String(v)
    }))
}

/** 审批决策 → 文案与配色 class（后端字段为 status: pending/approved/rejected，兼容 decision） */
const APPROVAL_LABEL_KEYS: Record<string, string> = {
  approved: 'chat.approvalApproved',
  rejected: 'chat.approvalRejected'
}
const claimApprovalValue = (approval: { status?: string | null; decision?: string | null }) =>
  approval.status || approval.decision || null
const claimApprovalLabel = (approval: { status?: string | null; decision?: string | null }) => {
  const key = APPROVAL_LABEL_KEYS[claimApprovalValue(approval) ?? '']
  if (key) return t(key)
  const value = claimApprovalValue(approval)
  return value === 'pending' ? t('chat.approvalPending') : value || '-'
}
const claimApprovalClass = (approval: { status?: string | null; decision?: string | null }) => {
  const value = claimApprovalValue(approval)
  return value === 'approved' ? 'st-ok' : value === 'rejected' ? 'st-fail' : 'st-draft'
}

/** 审批人：兼容 approver_name / approver.nickname 两种后端形态 */
const claimApproverName = (approval: NonNullable<ExpenseClaimDetailPayload['expense_claim']['approvals']>[number]) =>
  approval.approver_name || approval.approver?.nickname || approval.approver?.username || '-'

/** 进度卡片审批人（approver.nickname / username） */
const claimProgressApproverName = (
  approval: NonNullable<ReturnType<typeof progressView>>['approvals'][number]
) => approval.approver?.nickname || approval.approver?.username || '-'

/** 费用日期：只取日期部分（expense_date 是 00:00 的 ISO 串，避免时区偏移到隔天） */
const formatClaimDate = (value?: string | null): string => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** 明细金额合计（后端有 total_amount 时以它为准） */
const claimItemsSum = (claim: NonNullable<ReturnType<typeof claimDetailOf>>['expense_claim']) => {
  if (claim.total_amount != null && claim.total_amount !== '') return String(claim.total_amount)
  const sum = (claim.items ?? []).reduce(
    (acc, item) => acc + (Number(item.amount) || 0),
    0
  )
  return sum.toFixed(2)
}

/** 详情卡片聚合视图：数组字段统一兜底，模板里一次取全 */
const claimDetailView = (extra?: ChatMessageExtraData) => {
  const payload = claimDetailOf(extra)
  if (!payload) return null
  const claim = payload.expense_claim
  return {
    claim,
    items: Array.isArray(claim.items) ? claim.items : [],
    approvals: Array.isArray(claim.approvals) ? claim.approvals : [],
    attachments: Array.isArray(claim.attachments) ? claim.attachments : []
  }
}

// ===== 报销审批进度卡片（extra_data.ui_type = expense_progress） =====
const progressView = (extra?: ChatMessageExtraData) => {
  if (!extra || typeof extra !== 'object') return null
  const payload = extra as ExpenseClaimProgressPayload
  if (payload.ui_type !== 'expense_progress') return null
  const prog = payload.expense_progress
  if (!prog || typeof prog !== 'object' || typeof prog.claim_no !== 'string') return null
  return {
    ...prog,
    approvals: Array.isArray(prog.approvals) ? prog.approvals : []
  }
}

/** 时间线节点圆点配色：提交=通过绿，approved=绿，rejected=红，其余灰 */
const progressDotClass = (approval?: { status?: string | null; decision?: string | null }) => {
  const value = approval ? claimApprovalValue(approval) : 'submitted'
  return value === 'submitted' || value === 'approved'
    ? 'tl-ok'
    : value === 'rejected'
      ? 'tl-fail'
      : 'tl-draft'
}

/** 是否展示「等待审批」节点：单据仍在流转且最后一条记录不是驳回 */
const progressWaiting = (prog: NonNullable<ReturnType<typeof progressView>>) => {
  if (!['pending_approval', 'needs_info', 'processing'].includes(prog.status ?? '')) return false
  const last = prog.approvals[prog.approvals.length - 1]
  return !last || claimApprovalValue(last) !== 'rejected'
}

// ===== 报销审批历史卡片（extra_data.ui_type = expense_approval_history） =====
const historyView = (extra?: ChatMessageExtraData) => {
  if (!extra || typeof extra !== 'object') return null
  const payload = extra as ExpenseClaimApprovalHistoryPayload
  if (payload.ui_type !== 'expense_approval_history') return null
  const history = payload.expense_approval_history
  if (!history || typeof history !== 'object' || typeof history.claim_no !== 'string') return null
  return {
    ...history,
    approvals: Array.isArray(history.approvals) ? history.approvals : []
  }
}

// ===== 报销 AI 预审报告卡片（extra_data.ui_type = expense_pre_review） =====
const preReviewView = (extra?: ChatMessageExtraData) => {
  if (!extra || typeof extra !== 'object') return null
  const payload = extra as ExpensePreReviewPayload
  if (payload.ui_type !== 'expense_pre_review') return null
  const report = payload.expense_pre_review
  if (!report || typeof report !== 'object' || typeof report.claim_no !== 'string') return null
  const pr = report.pre_review
  const problems = pr?.result_data?.problems
  return {
    ...report,
    pre_review: pr ?? null,
    problems: Array.isArray(problems) ? problems : []
  }
}

// ===== 报销统计卡片（extra_data.ui_type = expense_statistics） =====
const statsView = (extra?: ChatMessageExtraData) => {
  if (!extra || typeof extra !== 'object') return null
  const payload = extra as ExpenseStatisticsPayload
  if (payload.ui_type !== 'expense_statistics') return null
  const currencies = Array.isArray(payload.currency_statistics) ? payload.currency_statistics : []
  const categories = Array.isArray(payload.category_statistics) ? payload.category_statistics : []
  const statusCounts = payload.status_counts && typeof payload.status_counts === 'object'
    ? payload.status_counts
    : {}
  const isEmpty = !currencies.length && !categories.length && !Object.keys(statusCounts).length
  return isEmpty ? null : { ...payload, currencies, categories, statusCounts }
}

/** 把可能为 null 的视图对象包装为数组，让模板 v-for 拿到非空类型 */
const asList = <T,>(value: T | null) => (value ? [value] : [])

/** 统计卡片：payload 合法且非空时返回单元素数组，便于模板中拿到非空类型 */
const statsList = (extra?: ChatMessageExtraData) => {
  const view = statsView(extra)
  return view ? [view] : []
}

/** 状态分布条：过滤 0 值、算占比、映射分段颜色 */
const STATUS_BAR_CLASS: Record<string, string> = {
  approved: 'bar-ok',
  completed: 'bar-ok',
  pending_approval: 'bar-pending',
  needs_info: 'bar-pending',
  rejected: 'bar-fail',
  failed: 'bar-fail',
  processing: 'bar-processing'
}
const statsStatusSegments = (counts: Record<string, number>) => {
  const entries = Object.entries(counts).filter(([, v]) => Number(v) > 0)
  const sum = entries.reduce((acc, [, v]) => acc + Number(v), 0) || 1
  return entries.map(([key, value]) => ({
    key,
    count: Number(value),
    pct: (Number(value) / sum) * 100,
    barClass: STATUS_BAR_CLASS[key] ?? 'bar-draft'
  }))
}

/** 分类汇总：按金额降序 + 占最大值比例（用于比例条） */
const statsCategories = (categories: ExpenseStatisticsPayload['category_statistics']) => {
  const list = (categories ?? []).filter(
    (c) => !!c && (Number(c.total_amount) || Number(c.item_count))
  )
  const max = Math.max(...list.map((c) => Number(c.total_amount) || 0), 0)
  return list
    .sort((a, b) => (Number(b.total_amount) || 0) - (Number(a.total_amount) || 0))
    .map((c) => ({ ...c, pct: max > 0 ? ((Number(c.total_amount) || 0) / max) * 100 : 0 }))
}

// 点击报销记录：打开只读详情抽屉（详情接口按 claim_no 查询）
const claimDrawerVisible = ref(false)
const activeClaimNo = ref<string | null>(null)
const openClaimDetail = (claim: ExpenseClaimCardItem) => {
  if (!claim?.claim_no) return
  activeClaimNo.value = claim.claim_no
  claimDrawerVisible.value = true
}

// ===== missing_fields 字段路径解析 =====
// 后端下发的是字段路径（expense_items / expense_items.{item_id}.{field}），
// 前端负责解析与中文映射；不认识的路径直接忽略，不报错。
const MISSING_FIELD_LABEL_KEYS: Record<string, string> = {
  category: 'chat.fieldCategory',
  amount: 'chat.fieldAmount',
  expense_date: 'chat.fieldExpenseDate',
  invoice: 'chat.fieldInvoice'
}

interface MissingFieldsParseResult {
  /** missing_fields 含裸路径 expense_items：尚未添加任何费用明细 */
  noExpenseItems: boolean
  /** item_id -> 缺失字段名列表（用 item_id 定位，不用数组下标） */
  itemFields: Record<string, string[]>
  /** 原始缺失路径总数 */
  count: number
}

const parseMissingFields = (missingFields?: string[] | null): MissingFieldsParseResult => {
  const result: MissingFieldsParseResult = { noExpenseItems: false, itemFields: {}, count: 0 }
  for (const field of missingFields ?? []) {
    result.count += 1
    if (field === 'expense_items') {
      result.noExpenseItems = true
      continue
    }
    const parts = field.split('.')
    if (parts.length !== 3 || parts[0] !== 'expense_items') continue
    const [, itemId, fieldName] = parts
    if (!MISSING_FIELD_LABEL_KEYS[fieldName]) continue
    if (!result.itemFields[itemId]) result.itemFields[itemId] = []
    if (!result.itemFields[itemId].includes(fieldName)) {
      result.itemFields[itemId].push(fieldName)
    }
  }
  return result
}

// ===== 右侧执行面板：真实运行指标 =====
// 指标来源优先级：SSE 推送的 run_completed.metrics > 最近一条 AI 消息的 extra_data.run_metrics
const latestRunMetrics = computed<RunMetrics | null>(() => {
  if (workflow.value?.metrics) return workflow.value.metrics
  // 运行中还没有本轮指标时不要回填上一轮，避免展示过期数字
  if (hasActiveRun.value) return null
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const msg = messages.value[i]
    if (msg.role !== 'ai') continue
    const raw = (msg.extraData as { run_metrics?: RunMetrics } | null)?.run_metrics
    if (raw) return raw
  }
  return null
})

/** 运行中每秒刷新一次时间戳，用于"已运行 N 秒"的实时计时 */
const nowTick = ref(Date.now())
let durationTimer: ReturnType<typeof setInterval> | null = null
watch(
  hasActiveRun,
  (active) => {
    if (active && !durationTimer) {
      nowTick.value = Date.now()
      durationTimer = setInterval(() => { nowTick.value = Date.now() }, 1000)
    } else if (!active && durationTimer) {
      clearInterval(durationTimer)
      durationTimer = null
    }
  },
  { immediate: true }
)
onBeforeUnmount(() => {
  if (durationTimer) { clearInterval(durationTimer); durationTimer = null }
})

const runStartedAtMs = computed<number | null>(() => {
  const raw = workflow.value?.startedAt
  if (!raw) return null
  const ms = new Date(raw).getTime()
  return Number.isNaN(ms) ? null : ms
})

/** 耗时：终态用后端返回的真实值，运行中用起点到当前的差值 */
const runDurationMs = computed<number | null>(() => {
  const finished = workflow.value?.durationMs
  if (typeof finished === 'number' && Number.isFinite(finished)) return finished
  if (!hasActiveRun.value) {
    // 非运行态（打开历史会话）：回退到最近一次运行记录的耗时
    const last = latestRunMetrics.value?.duration_ms
    return typeof last === 'number' ? last : null
  }
  const start = runStartedAtMs.value
  if (!start) return null
  return Math.max(nowTick.value - start, 0)
})

const runDurationLabel = computed(() => {
  const ms = runDurationMs.value
  if (ms === null) return '-'
  if (ms < 1000) return `${ms} ms`
  const seconds = ms / 1000
  if (seconds < 10) return `${seconds.toFixed(1)} s`
  if (seconds < 60) return `${Math.round(seconds)} s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  return `${minutes}m ${rest}s`
})

/** 执行引擎 = 本次真实使用的模型（后端配置），没有数据时不编造 */
const runEngineLabel = computed(
  () => workflow.value?.model || latestRunMetrics.value?.engine || '-'
)

const runTokenStats = computed<{
  total: number | null
  input: number | null
  output: number | null
}>(() => {
  const metrics = latestRunMetrics.value
  if (metrics && typeof metrics.total_tokens === 'number') {
    return {
      total: metrics.total_tokens,
      input: metrics.input_tokens ?? null,
      output: metrics.output_tokens ?? null
    }
  }
  // 兜底：取最近一条带 token 用量的 AI 消息（0 视为未统计，避免展示误导性的 0）
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const msg = messages.value[i]
    if (msg.role !== 'ai' || typeof msg.totalTokens !== 'number' || msg.totalTokens <= 0) continue
    return {
      total: msg.totalTokens,
      input: msg.inputTokens ?? null,
      output: msg.outputTokens ?? null
    }
  }
  return { total: null, input: null, output: null }
})

const runTokenLabel = computed(() =>
  typeof runTokenStats.value.total === 'number' ? formatToken(runTokenStats.value.total) : '-'
)
const runTokenSubLabel = computed(() =>
  typeof runTokenStats.value.input === 'number' || typeof runTokenStats.value.output === 'number'
    ? t('chat.tokenInputOutput', {
        input: formatToken(runTokenStats.value.input),
        output: formatToken(runTokenStats.value.output)
      })
    : 'tokens'
)

const runLlmCallsLabel = computed(() => {
  const calls = latestRunMetrics.value?.llm_calls
  return typeof calls === 'number' ? String(calls) : '-'
})
const runRagLabel = computed(() => {
  const metrics = latestRunMetrics.value
  const calls = metrics?.llm_calls
  if (typeof calls !== 'number') return '-'
  const hits = metrics?.rag_hits
  return typeof hits === 'number' && hits > 0
    ? t('chat.llmCallsSubWithRag', { count: hits })
    : t('chat.llmCallsSubNoRag')
})

// ===== 右侧"相关任务"面板 =====
const relatedTasks = ref<BusinessTaskCardItem[]>([])
const relatedTaskLoading = ref(false)
const activeTaskUid = ref<string | null>(null)

const loadRelatedTasks = async (conversationUid?: string | null) => {
  const uid = conversationUid ?? currentSessionId.value
  if (!uid) {
    relatedTasks.value = []
    activeTaskUid.value = null
    return
  }
  relatedTaskLoading.value = true
  try {
    const res = await getConversationBusinessTasksApi(uid)
    // 期间可能已切换会话，旧请求的结果直接丢弃
    if (uid !== currentSessionId.value) return
    const data = res?.data
    relatedTasks.value = Array.isArray(data?.items) ? data.items : []
    activeTaskUid.value = data?.active_business_task_uid ?? null
  } catch {
    if (uid === currentSessionId.value) {
      relatedTasks.value = []
      activeTaskUid.value = null
    }
  } finally {
    if (uid === currentSessionId.value) relatedTaskLoading.value = false
  }
}

const taskDisplayAmount = (task: BusinessTaskCardItem) => task.display?.total_amount ?? null
const taskDisplayItemCount = (task: BusinessTaskCardItem) => task.display?.item_count ?? 0
const taskClaimNo = (task: BusinessTaskCardItem) => task.display?.claim_no ?? null

/** 缺失字段路径 → 去重后的中文标签 */
const taskMissingLabels = (task: BusinessTaskCardItem): string[] => {
  const parsed = parseMissingFields(task.missing_fields)
  const labels = new Set<string>()
  if (parsed.noExpenseItems) labels.add(t('chat.fieldMissing'))
  for (const fields of Object.values(parsed.itemFields)) {
    for (const field of fields) {
      const key = MISSING_FIELD_LABEL_KEYS[field]
      if (key) labels.add(t(key))
    }
  }
  return [...labels]
}

/** 点击任务：已生成正式单的直接打开报销单详情；草稿态只做选中提示 */
const openRelatedTask = (task: BusinessTaskCardItem) => {
  const claimNo = taskClaimNo(task)
  if (claimNo) {
    openClaimDetail({ claim_no: claimNo } as ExpenseClaimCardItem)
    return
  }
  activeTaskUid.value = task.uid
}

// ===== 单任务卡片：以 display 为主数据源，draft_data 兜底 =====
interface TaskItemView {
  id: string
  /** 用途描述（缺失时用占位文案） */
  description: string
  categoryText: string
  categoryMissing: boolean
  amountText: string
  amountMissing: boolean
  dateText: string
  dateMissing: boolean
  /** 发票：missing_fields 含 invoice 路径即需要补充 */
  invoiceMissing: boolean
  invoiceCount: number
  /** 已上传发票的文件名（hover 时的 tooltip） */
  invoiceFileNames: string[]
  /** 该条明细缺失字段的中文名 */
  missingLabels: string[]
}

interface CurrentTaskView {
  title: string
  uid: string
  status: string
  claimStatus: string | null
  claimNo: string | null
  totalText: string
  itemCount: number
  createdAtText: string
  items: TaskItemView[]
  /** 缺失字段路径总数（后端原值） */
  missingCount: number
  /** 去重后的缺失字段中文名，用于汇总提示 */
  missingLabelsText: string
}

const EMPTY_TASK_VIEW: CurrentTaskView = {
  title: '',
  uid: '',
  status: '',
  claimStatus: null,
  claimNo: null,
  totalText: '-',
  itemCount: 0,
  createdAtText: '-',
  items: [],
  missingCount: 0,
  missingLabelsText: ''
}

/** 货币符号：未知币种直接前缀币种代码，避免金额失去单位 */
const CURRENCY_SYMBOL: Record<string, string> = {
  CNY: '¥',
  RMB: '¥',
  USD: '$',
  EUR: '€',
  HKD: 'HK$',
  JPY: '¥'
}

/** 金额格式化：后端下发字符串（"600.00"），统一加货币符号与千分位 */
const formatMoney = (value?: string | number | null, currency?: string | null): string => {
  if (value === null || value === undefined || value === '') return '-'
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num)) return '-'
  const code = (currency || 'CNY').toUpperCase()
  const symbol = CURRENCY_SYMBOL[code] ?? `${code} `
  return `${symbol}${num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`
}

/** 日期展示：date-only 原样返回，ISO 时间取本地日期，非法值返回占位 */
const formatDate = (value?: string | null): string => {
  if (!value) return '-'
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** 字段路径里的字段名 → 中文标签（未知字段返回空串，由调用方忽略） */
const missingFieldLabel = (field: string) => {
  if (field === 'expense_items') return t('chat.taskExpenseDetail')
  const key = MISSING_FIELD_LABEL_KEYS[field]
  return key ? t(key) : ''
}

/**
 * 任务列表卡片的摘要元信息：N 笔 · 类别（多笔时追加"等"） · 日期。
 * 列表卡片不展开明细，但这几项足够让用户区分每一笔报销。
 */
const taskListMeta = (task: BusinessTaskCardItem): string => {
  const summary = (task.display?.expense_summary ?? []).filter(
    (item): item is ExpenseItemDraft => !!item && typeof item === 'object'
  )
  const count = task.display?.item_count ?? summary.length
  const parts: string[] = []
  if (typeof count === 'number' && Number.isFinite(count) && count > 0) {
    const unit = t('chat.taskItemUnit')
    parts.push(unit ? `${count} ${unit}` : String(count))
  }
  const first = summary[0]
  const label = first?.category || first?.description || ''
  if (label) {
    parts.push(summary.length > 1 ? `${label}${t('chat.taskMetaEtc')}` : label)
  }
  const date = formatDate(task.display?.created_at)
  if (date !== '-') parts.push(date)
  return parts.join(' · ') || '-'
}

/** display 未下发金额时，用明细金额求和兜底 */
const sumItemAmounts = (items: ExpenseItemDraft[]) =>
  items.reduce((sum, item) => {
    const num = Number(item.amount)
    return sum + (Number.isFinite(num) ? num : 0)
  }, 0)

const computeTaskView = (task: BusinessTaskCardItem): CurrentTaskView => {
  const display = task.display ?? null
  const parsed = parseMissingFields(task.missing_fields)

  // 明细优先用 display.expense_summary（后端口径统一），没有再退回 draft_data
  const summaryItems = (display?.expense_summary ?? []).filter(
    (item): item is ExpenseItemDraft => !!item && typeof item === 'object'
  )
  const sourceItems = summaryItems.length
    ? summaryItems
    : task.draft_data?.expense_items ?? []

  const items: TaskItemView[] = sourceItems.map((item, index) => {
    const missing = parsed.itemFields[item.id] ?? []
    const categoryMissing = missing.includes('category')
    const amountMissing = missing.includes('amount')
    const dateMissing = missing.includes('expense_date')
    const invoiceCount =
      typeof item.invoice_count === 'number' && Number.isFinite(item.invoice_count)
        ? item.invoice_count
        : item.attachments?.length ?? 0
    return {
      id: item.id || `item-${index}`,
      description: (item.description ?? '').trim() || t('chat.taskUntitledItem'),
      categoryText: categoryMissing ? t('chat.fieldMissing') : item.category || '—',
      categoryMissing,
      amountText: amountMissing ? t('chat.fieldMissing') : formatMoney(item.amount, display?.currency),
      amountMissing,
      dateText: dateMissing ? t('chat.fieldMissing') : formatDate(item.expense_date),
      dateMissing,
      invoiceMissing: missing.includes('invoice'),
      invoiceCount,
      invoiceFileNames: (item.attachments ?? [])
        .map((file) => (file?.filename ?? '').trim())
        .filter((name) => !!name),
      missingLabels: missing.map(missingFieldLabel).filter((label) => !!label)
    }
  })

  // 汇总提示里的字段名去重，保持 missing_fields 原顺序
  const missingLabels: string[] = []
  for (const path of task.missing_fields ?? []) {
    const parts = path.split('.')
    if (parts.length !== 3) {
      if (path === 'expense_items') missingLabels.push(missingFieldLabel(path))
      continue
    }
    const label = missingFieldLabel(parts[2])
    if (label && !missingLabels.includes(label)) missingLabels.push(label)
  }

  const totalAmount = display?.total_amount ?? sumItemAmounts(sourceItems)

  return {
    title: display?.display_title || task.title || '-',
    uid: task.uid,
    status: task.status,
    claimStatus: task.claim_status ?? null,
    claimNo: display?.claim_no ?? null,
    totalText: formatMoney(totalAmount, display?.currency),
    itemCount: display?.item_count ?? items.length,
    createdAtText: formatDate(display?.created_at),
    items,
    missingCount: parsed.count,
    missingLabelsText: missingLabels.join('、')
  }
}

// 卡片数据按 task 对象缓存，避免模板里多次取值重复计算；切换语言后失效重算
const taskViewCache = new WeakMap<BusinessTaskCardItem, { locale: string; view: CurrentTaskView }>()

const buildCurrentTaskView = (task: BusinessTaskCardItem | null): CurrentTaskView => {
  if (!task) return EMPTY_TASK_VIEW
  const cached = taskViewCache.get(task)
  if (cached && cached.locale === locale.value) return cached.view
  const view = computeTaskView(task)
  taskViewCache.set(task, { locale: locale.value, view })
  return view
}

/** 模板入口：从消息的 extra_data 取任务并构建展示视图 */
const taskView = (msg: Message) => buildCurrentTaskView(taskOf(msg.extraData))

/** 复制文本（优先 Clipboard API，非安全上下文回退到临时 textarea） */
const copyText = async (text?: string) => {
  if (!text) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success(t('chat.copySuccess'))
  } catch {
    ElMessage.error(t('chat.copyFailed'))
  }
}

// ===== 发票上传（卡片明细行内入口） =====
// 后端允许上传的任务状态（其余状态点击会 409，前端直接禁用）
const INVOICE_UPLOADABLE_STATUSES = ['collecting', 'waiting_confirmation']
const canUploadInvoice = (status?: string) =>
  !!status && INVOICE_UPLOADABLE_STATUSES.includes(status)

// 手机相册里的照片可能被标成 image/heic、image/*，所以放开到图片全类型，
// 由 normalizeInvoiceFile 统一转成 JPEG 后再交给后端（后端仍只收 pdf/jpg/png）
const INVOICE_ACCEPT = 'image/*,.pdf,application/pdf'

// 正在上传发票的明细 id：按钮转 loading，其他明细的上传按钮不受影响
const uploadingItemUid = ref<string | null>(null)

/**
 * 上传发票成功后刷新会话消息。
 *
 * 后端在这次上传里已经写入一条 assistant 消息（带最新任务卡片 extra_data），
 * 所以这里直接重新拉取消息列表即可，不再由前端自行拼装任务数据。
 */
const refreshAfterInvoiceUpload = async (conversationUid: string) => {
  await fetchMessages(conversationUid)
}

/**
 * 选中文件后上传。
 *
 * msg / item 由模板直接传入（不再依赖「先点按钮记录目标」的中转状态），
 * 这样即使选择器打开期间消息列表被刷新、组件重渲染，也不会丢失上传目标。
 */
const onInvoiceFileChange = async (event: Event, msg: Message, item: TaskItemView) => {
  const input = event.target as HTMLInputElement
  const picked = Array.from(input.files ?? [])
  // 先重置 value，保证同一文件可以重复选择
  input.value = ''

  // 用户在有选择器的情况下取消选择：静默返回（不做任何提示）
  if (!picked.length) return

  const conversationUid = currentSessionId.value
  const taskUid = taskView(msg).uid
  if (!conversationUid || !taskUid || uploadingItemUid.value) return

  uploadingItemUid.value = item.id
  let uploadedCount = 0
  let rejectedCount = 0

  try {
    // 多选时逐个上传；失败即中断，已成功的部分仍然生效
    for (const raw of picked) {
      // 手机原图先归一化：HEIC/WebP/超大图 → JPEG，避免后端 415 或超过 10MB
      const file = await normalizeInvoiceFile(raw)
      if (!isSupportedInvoiceFile(file)) {
        rejectedCount += 1
        continue
      }
      await uploadExpenseItemAttachmentApi(conversationUid, taskUid, item.id, file)
      uploadedCount += 1
    }
  } catch (error: any) {
    // HTTP 错误提示由统一拦截器给出（含 detail 兜底），这里只需兜住非 HTTP 异常
    if (!error?.response) {
      ElMessage.error(error?.message || t('chat.invoiceUploadFailed'))
    }
  } finally {
    if (uploadedCount) {
      ElMessage.success(t('chat.invoiceUploadSuccess', { count: uploadedCount }))
      // 后端会为本次上传追加一条 assistant 消息，重新拉取列表把新消息和新卡片带出来
      await refreshAfterInvoiceUpload(conversationUid)
    } else if (rejectedCount) {
      // 前端能识别但格式不支持（如无法解码的 HEIC）：明确告知，避免「点了没反应」
      ElMessage.error(t('chat.invoiceUploadFailed'))
    }
    uploadingItemUid.value = null
  }
}

// 正在提交选择的任务 uid：点击后禁用其他卡片，避免重复提交
const selectingTaskUid = ref<string | null>(null)

/** 列表卡片允许携带的选择动作（与后端 _build_task_list_ui_payload 的 allowed_actions 对齐） */
const TASK_LIST_ACTIONS = ['select_business_task', 'select_resume_task']

/**
 * 点击任务列表卡片。
 * 提交的 action 取自下发这份列表的 AI 消息 extra_data.action
 * （任务选择列表是 select_business_task，恢复任务列表是 select_resume_task），
 * extra_data 未携带时回退为 select_business_task 兼容旧消息。
 */
const handleSelectBusinessTask = async (task: BusinessTaskCardItem, extra?: ChatMessageExtraData) => {
  if (!task?.uid || selectingTaskUid.value || loading.value || hasActiveRun.value) return
  const payloadAction = (extra as { action?: string } | null)?.action
  const action =
    payloadAction && TASK_LIST_ACTIONS.includes(payloadAction)
      ? payloadAction
      : 'select_business_task'
  selectingTaskUid.value = task.uid
  try {
    await sendUserMessage(t('chat.taskSelectMessage', { title: task.title }), {
      action,
      selected_task_uid: task.uid
    })
  } finally {
    selectingTaskUid.value = null
  }
}

const formatToken = (value?: number | null) =>
  typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : '-'

const startNewChat = () => {
  // 新建对话时关闭上一会话的订阅，避免事件写入新窗口
  stopWorkflow()
  // 右侧"相关任务"属于会话维度，新建时清空
  relatedTasks.value = []
  activeTaskUid.value = null
  // 停止仍在进行的打字机与延后刷新
  stopTypingPump()
  deferredRefresh = null
  sessionStorage.removeItem(LAST_CONVERSATION_KEY)
  // 退出搜索态：新会话不应被搜索词过滤掉
  clearSearch()
  currentSessionId.value = null
  runProgressVisible.value = false
  messages.value = []
  processSteps.value = [
    { key: 'idle', title: t('chat.waitingInput'), time: '-', desc: t('chat.ready'), type: 'info', hollow: true }
  ]
}

// 加载指定会话的历史消息（参数为会话 uid）
// forceBottom：切换会话时强制定位到最新消息；否则只在用户原本就贴近底部时跟随
const fetchMessages = async (conversationUid: string, forceBottom = false) => {
  try {
    const res = await getConversationMessagesApi(conversationUid)
    // 请求返回时会话可能已切换，丢弃过期结果
    if (currentSessionId.value !== conversationUid) return
    // 仍在逐字输出时不做整体替换，避免把正在显示的回复冲掉（吐完后会自动对齐一次）
    if (messages.value.some((m) => m.streaming)) {
      if (forceBottom || isNearBottom.value) void scrollToBottom(false)
      return
    }
    if (res.code === 0 || res.code === 200) {
      // 保留 SSE 已拿到的 Token 用量：接口未统计（null）时不覆盖已有值
      const previousByUid = new Map(
        messages.value.filter((m) => m.uid).map((m) => [m.uid as string, m])
      )
      // 将后端消息映射为前端展示结构
      messages.value = res.data.items.map(item => {
        const previous = previousByUid.get(item.uid)
        return {
          uid: item.uid,
          role: item.role === 'user' ? 'user' : 'ai',
          time: new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          type: 'text',
          content: item.content,
          inputTokens: item.input_tokens ?? previous?.inputTokens ?? null,
          outputTokens: item.output_tokens ?? previous?.outputTokens ?? null,
          totalTokens: item.total_tokens ?? previous?.totalTokens ?? null,
          // 卡片数据以数据库结果为准，接口未返回时保留 SSE 已拿到的值
          extraData: item.extra_data ?? previous?.extraData ?? null
        } as Message
      })
      // 进入/切换会话后定位到最新一条消息；运行结束刷新时若用户正在翻阅历史则不打断
      if (forceBottom || isNearBottom.value) void scrollToBottom(false)
    } else {
      console.warn('加载消息失败', res.msg)
    }
  } catch (error) {
    console.error('加载历史消息失败', error)
    ElMessage.error(t('chat.loadMsgsFailed'))
  }
}

// 恢复会话中未结束的工作流：先核对真实状态，再决定是否重新订阅
const restoreActiveRun = async (conversationUid: string) => {
  const runUid = readActiveRun(conversationUid)
  if (!runUid) return

  try {
    const res = await getWorkflowRunStatusApi(conversationUid, runUid)
    const data = res?.data
    if (!data || data.run_uid !== runUid || isTerminalStatus(data.status)) {
      // 已经结束的工作流直接清除缓存，结果以历史消息为准
      clearActiveRun(conversationUid)
      return
    }
    if (currentSessionId.value !== conversationUid) return
    // 恢复未结束的工作流时，中间区域重新展示进度块
    runProgressVisible.value = true
    // SSE 不提供事件回放，刷新后只能按当前状态重建一个占位节点
    processSteps.value = [
      {
        key: 'run:restore',
        title: t('chat.stepAiProcessing'),
        time: nowTimeLabel(),
        desc: statusLabels.value[data.status],
        type: 'primary',
        color: '#ff5c33',
        state: 'running'
      }
    ]
    startWorkflow(conversationUid, runUid, data.status)
  } catch (error) {
    console.error('恢复工作流状态失败', error)
    clearActiveRun(conversationUid)
  }
}

// 切换会话：关闭旧订阅、加载历史消息、按需恢复未结束的工作流
const handleSelectSession = async (sessionUid: string) => {
  if (currentSessionId.value === sessionUid) return
  stopWorkflow()
  // 切换会话时停止上一个会话的打字机，防止旧会话文字继续写入新窗口
  stopTypingPump()
  deferredRefresh = null
  currentSessionId.value = sessionUid
  sessionStorage.setItem(LAST_CONVERSATION_KEY, sessionUid)
  runProgressVisible.value = false
  messages.value = []
  processSteps.value = [
    { key: 'idle', title: t('chat.stepReceive'), time: '-', desc: t('chat.waitingInput'), type: 'info', hollow: true }
  ]
  await fetchMessages(sessionUid, true)
  await restoreActiveRun(sessionUid)
  void loadRelatedTasks(sessionUid)
}

const fetchSessions = async (autoSelect = true) => {
  try {
    const res = await getConversationsApi()
    if (res.code === 0 || res.code === 200) {
      sessions.value = res.data.items.map(toSession)
      totalConversations.value = res.data.total

      // autoSelect=false：从工作台带消息跳转而来，直接进入新会话，不恢复历史会话
      if (!autoSelect) return

      // 优先恢复上次打开的会话（刷新页面后可继续恢复其未完成的工作流），否则选最新会话
      const lastUid = sessionStorage.getItem(LAST_CONVERSATION_KEY)
      const targetUid = sessions.value.some((s) => s.uid === lastUid)
        ? lastUid
        : sessions.value[0]?.uid
      if (targetUid && currentSessionId.value === null) {
        await handleSelectSession(targetUid)
      }
    }
  } catch (error) {
    console.error('获取会话列表失败', error)
  }
}

const handleSend = async () => {
  const content = inputMsg.value.trim()
  // 发送中或当前会话仍有未结束的工作流时，阻止重复提交
  if (!content || loading.value || hasActiveRun.value) return

  inputMsg.value = ''
  await sendUserMessage(content)
}

/**
 * 统一的发送流程：聊天输入与任务卡片点击共用。
 * extra 用于携带业务动作（action / selected_task_uid），不传时即普通聊天消息。
 */
const sendUserMessage = async (content: string, extra?: Pick<MessageSendOptions, 'action' | 'selected_task_uid'>) => {
  if (!content || loading.value || hasActiveRun.value) return

  loading.value = true

  try {
    // 1. 没有当前会话时先创建
    if (currentSessionId.value === null) {
      const convRes = await createConversationApi({ title: content.slice(0, 20) })
      if (!(convRes.code === 0 || convRes.code === 200 || convRes.code === 201)) {
        throw new Error(convRes.msg || t('chat.createSessionFailed'))
      }
      const newSession: Session = {
        uid: convRes.data.uid,
        name: convRes.data.title,
        time: nowTimeLabel()
      }
      sessions.value.unshift(newSession)
      // 首次提问会新建会话，退出搜索态才能在侧栏看到它
      if (isSearchMode.value) clearSearch()
      currentSessionId.value = newSession.uid
      sessionStorage.setItem(LAST_CONVERSATION_KEY, newSession.uid)
    }

    const conversationUid = currentSessionId.value

    // 2. 立即展示用户消息（等后端返回后再用真实 uid 补全）
    const userMsg: Message = {
      uid: undefined,
      role: 'user',
      time: nowTimeLabel(),
      type: 'text',
      content
    }
    messages.value.push(userMsg)
    const optimisticIndex = messages.value.length - 1
    // 发送后强制回到底部，保证用户能立刻看到自己的消息与后续 AI 回复
    void scrollToBottom()

    processSteps.value = [
      { key: 'run:sent', title: t('chat.stepSent'), time: userMsg.time, desc: t('chat.stepSentDesc'), type: 'success', color: '#2ecc71', state: 'success' }
    ]
    runProgressVisible.value = true

    // 3. 提交消息并获取本次工作流运行标识（选择任务时带上业务动作）
    const sendRes = await sendMessageApi(conversationUid, { content, ...extra })
    if (!(sendRes.code === 0 || sendRes.code === 200)) {
      throw new Error(sendRes.msg || t('chat.sendFailed'))
    }
    const data = sendRes.data

    // 用后端返回的消息替换本地乐观数据
    if (currentSessionId.value === conversationUid) {
      messages.value[optimisticIndex] = {
        uid: data.user_message.uid,
        role: 'user',
        time: new Date(data.user_message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        type: 'text',
        content: data.user_message.content
      }
    }

    // 4. 记录并订阅工作流进度（AI 回复通过 SSE 推送，不再等待接口返回值）
    saveActiveRun(conversationUid, data.run.uid)
    startWorkflow(data.conversation_uid, data.run.uid, data.run.status)

    // 5. 发送接口若同步返回了回复（当前后端为 null），按消息展示
    if (data.assistant_message) {
      applyAssistantMessage(data.run.uid, {
        message_uid: data.assistant_message.uid,
        content: data.assistant_message.content,
        input_tokens: data.assistant_message.input_tokens ?? null,
        output_tokens: data.assistant_message.output_tokens ?? null,
        total_tokens: data.assistant_message.total_tokens ?? null,
        extra_data: data.assistant_message.extra_data ?? null
      })
    }
  } catch (error: any) {
    ElMessage.error(error?.message || t('chat.sendFailed'))
    console.error(error)
    // 发送失败：移除本地乐观消息，避免出现无法对应的气泡
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'user' && !last.uid) {
      messages.value.pop()
    }
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  // 支持从其它页面（如员工工作台）携带 autoSend 消息跳转进入并自动发送
  const autoSend = typeof route.query.autoSend === 'string' ? route.query.autoSend.trim() : ''
  if (autoSend) {
    startNewChat()
    // 只拉会话列表，不自动恢复最近会话，保证消息进入全新会话
    await fetchSessions(false)
    await sendUserMessage(autoSend)
    // 清掉 query，避免刷新 / 前进后退时重复发送
    void router.replace({ path: '/ai-chat' })
    void scrollToBottom(false)
    return
  }
  void fetchSessions()
  void scrollToBottom(false)
})

onBeforeUnmount(() => {
  stopTypingPump()
  deferredRefresh = null
  // 离开页面时清掉搜索防抖，避免卸载后仍发请求
  if (searchTimer) { clearTimeout(searchTimer); searchTimer = null }
})
</script>

<style scoped>
.ai-chat-container {
  display: flex;
  height: 100%;
  background: var(--af-bg);
  overflow: hidden;
}
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--af-success); }

/* ===== 左侧会话栏 ===== */
.chat-sessions-sidebar {
  width: 248px;
  flex-shrink: 0;
  background: #0d0d0d;
  border-right: 1px solid var(--af-border-soft);
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 16px 16px 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.sidebar-title {
  display: flex; align-items: center; gap: 8px;
  font-weight: 700; font-size: 14px; color: var(--af-text);
}
.new-chat-btn {
  width: 30px; height: 30px;
  border-radius: 9px;
  background: var(--af-primary-gradient);
  border: none; color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; cursor: pointer;
}

.session-search {
  margin: 0 12px 10px;
  display: flex; align-items: center; gap: 8px;
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 9px;
  padding: 7px 11px;
  color: var(--af-text-3);
}
.session-search input {
  flex: 1; min-width: 0;
  background: transparent; border: none; outline: none;
  color: var(--af-text); font-size: 12px;
}
/* 搜索请求中的小 spinner / 清空按钮（与输入框同一行） */
.search-spin { font-size: 12px; color: var(--af-text-3); flex-shrink: 0; }
.search-clear {
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; padding: 0; border: none; border-radius: 50%;
  background: var(--af-border-soft); color: var(--af-text-3);
  font-size: 10px; cursor: pointer; flex-shrink: 0; transition: all 0.15s;
}
.search-clear:hover { background: var(--af-text-3); color: var(--af-card); }
/* 搜索结果条数提示 */
.search-meta {
  display: flex; justify-content: space-between; gap: 6px;
  margin: 0 14px 6px; font-size: 11px; color: var(--af-text-3);
}
.search-meta-more { flex-shrink: 0; }
/* 标题命中关键词高亮 */
.session-hit {
  background: transparent; color: var(--af-primary);
  font-weight: 600; padding: 0;
}
.empty-clear {
  margin-left: 6px; padding: 0; border: none; background: transparent;
  color: var(--af-primary); font-size: 12px; cursor: pointer;
}
.empty-clear:hover { text-decoration: underline; }

.session-list { flex: 1; overflow-y: auto; padding: 0 10px; }
.session-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 11px 12px;
  border-radius: 10px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: all 0.15s;
  border-left: 2px solid transparent;
}
.session-item:hover { background: var(--af-hover); }
.session-item.active {
  background: var(--af-card-soft);
  border-left-color: var(--af-primary);
}
.session-info { flex: 1; min-width: 0; overflow: hidden; }
.session-name {
  font-size: 13px; color: var(--af-text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.session-item.active .session-name { color: var(--af-primary); }
.session-preview {
  font-size: 11px; color: var(--af-text-3); margin-top: 3px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.session-empty { text-align: center; color: var(--af-text-3); font-size: 12px; padding: 30px 0; }

/* 会话行操作：hover / 选中时浮出，触屏常显 */
.session-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}
.session-item:hover .session-actions,
.session-item.active .session-actions { opacity: 1; }
.session-action-btn {
  width: 24px; height: 24px;
  padding: 0;
  display: flex; align-items: center; justify-content: center;
  border: none; border-radius: 6px;
  background: transparent;
  color: var(--af-text-3);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.session-action-btn:hover { background: var(--af-card); color: var(--af-text); }
.session-action-btn.danger:hover { background: rgba(231, 76, 60, 0.14); color: #e74c3c; }
@media (hover: none) {
  .session-actions { opacity: 1; }
}

/* 行内重命名 */
.session-rename { flex: 1; min-width: 0; }
.session-rename-input {
  width: 100%;
  padding: 3px 7px;
  font-size: 13px;
  color: var(--af-text);
  background: var(--af-card);
  border: 1px solid var(--af-primary);
  border-radius: 6px;
  outline: none;
}

/* 无会话引导 */
.session-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 36px 16px;
  text-align: center;
}
.empty-illustration {
  width: 52px; height: 52px;
  margin-bottom: 8px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 16px;
  background: var(--af-primary-soft);
  border: 1px dashed var(--af-border);
  color: var(--af-primary);
  font-size: 22px;
}
.empty-title { color: var(--af-text-2); font-size: 13px; font-weight: 600; }
.empty-desc { color: var(--af-text-3); font-size: 11px; line-height: 1.7; max-width: 180px; }

.sidebar-foot {
  padding: 12px 16px;
  border-top: 1px solid var(--af-border-soft);
  display: flex; align-items: center; gap: 7px;
  color: var(--af-text-3); font-size: 11px;
}

/* ===== 中间聊天区 ===== */
.chat-main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--af-bg-soft);
  min-width: 0;
  position: relative;
}

/* 回到底部悬浮按钮：锚定在输入框容器上方，与输入框间距固定，不随端别写死偏移 */
.scroll-bottom-btn {
  position: absolute;
  left: 50%;
  top: -40px;
  transform: translateX(-50%);
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 999px;
  border: 1px solid var(--af-border);
  background: var(--af-card);
  color: var(--af-text-2);
  font-size: 12px;
  cursor: pointer;
  box-shadow: var(--af-shadow, 0 6px 18px rgba(0, 0, 0, 0.28));
  z-index: 5;
  transition: color 0.15s, border-color 0.15s;
}
.scroll-bottom-btn:hover { color: var(--af-primary); border-color: var(--af-primary); }
.fade-enter-active, .fade-leave-active { transition: opacity 0.18s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.chat-header {
  padding: 14px 20px;
  border-bottom: 1px solid var(--af-border-soft);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 12px; min-width: 0; }
/* 移动端会话入口：悬浮在聊天区左上角头像列内（0~58px 留白带），不压 AI 气泡 */
.mobile-sessions-fab {
  display: none;
  align-items: center;
  gap: 2px;
  position: absolute;
  top: 10px;
  left: 6px;
  z-index: 6;
  height: 26px;
  padding: 0 7px;
  border-radius: 999px;
  border: 1px solid var(--af-border-soft);
  background: rgba(13, 13, 13, 0.82);
  color: var(--af-text-2);
  font-size: 11px;
  cursor: pointer;
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  transition: color 0.15s, border-color 0.15s;
}
.mobile-sessions-fab .fab-arrow { font-size: 10px; }
.mobile-sessions-fab:active { color: var(--af-primary); border-color: var(--af-primary); }

/* 会话抽屉：teleport 到 body，scoped 样式够不到，用 :global 清掉默认内边距让内容撑满 */
:global(.af-sessions-drawer .el-drawer__body) {
  padding: 0;
}
.chat-title {
  font-size: 16px; font-weight: 700; color: var(--af-text); margin: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  display: flex; align-items: center; gap: 8px;
}
.edit-icon { color: var(--af-text-3); font-size: 14px; cursor: pointer; flex-shrink: 0; }
.chat-tag {
  display: flex; align-items: center; gap: 7px;
  color: var(--af-text-2); font-size: 12px;
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 20px;
  padding: 5px 13px;
  flex-shrink: 0;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 26px;
}

.chat-welcome {
  margin: auto;
  text-align: center;
  color: var(--af-text-3);
}
.welcome-icon {
  width: 56px; height: 56px; margin: 0 auto 14px;
  border-radius: 16px;
  background: var(--af-primary-soft);
  color: var(--af-primary);
  display: flex; align-items: center; justify-content: center;
  font-size: 26px;
}
.chat-welcome h3 { color: var(--af-text); font-size: 17px; margin-bottom: 8px; }
.chat-welcome p { font-size: 12px; }
/* 空会话引导：可点击的示例问题 */
.welcome-suggestions {
  display: flex; flex-direction: column; align-items: stretch; gap: 10px;
  width: 300px; max-width: 82vw;
  margin: 22px auto 0; text-align: left;
}
.welcome-chip {
  display: inline-flex; align-items: center; gap: 9px;
  padding: 11px 16px;
  font-size: 13px; color: var(--af-text-2);
  background: var(--af-card, var(--af-hover));
  border: 1px solid var(--af-border-soft);
  border-radius: 12px;
  cursor: pointer; text-align: left;
  transition: all 0.18s ease;
}
.welcome-chip .el-icon { color: var(--af-text-3); transition: color 0.18s ease; flex-shrink: 0; }
.welcome-chip:hover:not(:disabled) {
  color: var(--af-text);
  border-color: rgba(255, 92, 51, 0.4);
  background: var(--af-primary-soft);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.18);
}
.welcome-chip:hover:not(:disabled) .el-icon { color: var(--af-primary); }
.welcome-chip:disabled { opacity: 0.55; cursor: not-allowed; }

.message-wrapper {
  display: flex;
  gap: 10px;
  max-width: 86%;
}
.message-wrapper.user {
  flex-direction: row-reverse;
  align-self: flex-end;
}

.avatar-badge {
  width: 34px; height: 34px; flex-shrink: 0;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 700;
}
.avatar-badge.ai { background: var(--af-primary-gradient); color: #fff; }
.avatar-badge.user { background: var(--af-hover); color: var(--af-text-2); }

.message-content-group { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.message-wrapper.user .message-content-group { align-items: flex-end; }

.message-meta { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--af-text-3); }
.message-author { color: var(--af-text-2); font-weight: 600; }
.llm-tag {
  font-size: 10px; color: var(--af-text-3);
  border: 1px solid var(--af-border);
  border-radius: 4px; padding: 0 5px;
}

.message-content { display: flex; flex-direction: column; gap: 10px; max-width: 100%; }

.text-box {
  padding: 15px 19px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.7;
  max-width: fit-content;
  word-break: break-word;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.ai .text-box {
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  color: var(--af-text);
  border-top-left-radius: 4px;
}
/* AI 消息 Markdown 正文：接管排版，关闭气泡的 pre-wrap（markdown 已自带结构） */
.text-box.md-body {
  white-space: normal;
  max-width: min(760px, 100%);
  display: block;
}
.md-content {
  line-height: 1.7;
  word-break: break-word;
  overflow-wrap: anywhere;
}
.md-content :deep(p) { margin: 0 0 8px; }
.md-content :deep(p:last-child) { margin-bottom: 0; }
.md-content :deep(strong) { color: var(--af-text); font-weight: 600; }
.md-content :deep(em) { color: var(--af-text-2); }
.md-content :deep(a) { color: var(--af-primary, #ff7a45); text-decoration: none; }
.md-content :deep(a:hover) { text-decoration: underline; }
.md-content :deep(h1),
.md-content :deep(h2),
.md-content :deep(h3),
.md-content :deep(h4),
.md-content :deep(h5) {
  margin: 14px 0 8px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--af-text);
}
.md-content :deep(h1) { font-size: 18px; }
.md-content :deep(h2) { font-size: 17px; }
.md-content :deep(h3) { font-size: 15px; }
.md-content :deep(h4), .md-content :deep(h5) { font-size: 14px; }
.md-content :deep(h1:first-child),
.md-content :deep(h2:first-child),
.md-content :deep(h3:first-child) { margin-top: 0; }
.md-content :deep(ul) { list-style: disc outside; margin: 4px 0 10px; padding-left: 22px; }
.md-content :deep(ol) { list-style: decimal outside; margin: 4px 0 10px; padding-left: 26px; }
.md-content :deep(li) { margin: 3px 0; display: list-item; }
.md-content :deep(li > ul) { list-style: circle outside; margin: 3px 0; }
.md-content :deep(li > ol) { margin: 3px 0; }
.md-content :deep(li > p) { margin: 0; }
.md-content :deep(li::marker) { color: var(--af-text-3); }
.md-content :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--af-primary, #ff7a45);
  background: color-mix(in srgb, var(--af-primary, #ff7a45) 8%, transparent);
  border-radius: 0 8px 8px 0;
  color: var(--af-text-2);
}
.md-content :deep(blockquote p) { margin: 0; }
.md-content :deep(code) {
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12.5px;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid var(--af-border-soft);
  border-radius: 5px;
  padding: 1px 6px;
}
.md-content :deep(pre) {
  margin: 8px 0 10px;
  padding: 12px 14px;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid var(--af-border-soft);
  border-radius: 10px;
  overflow-x: auto;
}
.md-content :deep(pre code) {
  background: transparent;
  border: none;
  padding: 0;
  font-size: 12.5px;
  line-height: 1.6;
}
.md-content :deep(table) {
  border-collapse: collapse;
  margin: 8px 0 12px;
  width: 100%;
  font-size: 13px;
}
.md-content :deep(th),
.md-content :deep(td) {
  border: 1px solid var(--af-border-soft);
  padding: 6px 10px;
  text-align: left;
}
.md-content :deep(th) { background: rgba(255, 255, 255, 0.05); font-weight: 600; }
.md-content :deep(hr) { border: none; border-top: 1px solid var(--af-border-soft); margin: 12px 0; }
.md-content :deep(img) { max-width: 100%; border-radius: 8px; }

/* 知识库引用来源卡片（ui_type = knowledge_sources） */
.ks-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 14px;
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 12px;
  max-width: min(760px, 100%);
}
.ks-group { min-width: 0; }
.ks-doc {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  background: none;
  border: none;
  padding: 0;
  margin-bottom: 6px;
  min-width: 0;
  cursor: pointer;
  text-align: left;
  color: inherit;
  font: inherit;
}
.ks-doc:hover .ks-doc-title { color: var(--af-primary); }
.ks-caret {
  margin-left: auto;
  flex-shrink: 0;
  color: var(--af-text-3);
  font-size: 13px;
  transition: transform 0.15s ease;
}
.ks-doc-icon { color: var(--af-text-2); font-size: 15px; flex-shrink: 0; }
.ks-doc-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--af-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ks-kb {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--af-text-3);
  border: 1px solid var(--af-border-soft);
  border-radius: 5px;
  padding: 0 6px;
  line-height: 18px;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ks-rows {
  margin-left: 7px;
  padding-left: 12px;
  border-left: 1px solid var(--af-border-soft);
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.ks-row {
  display: flex;
  align-items: center;
  gap: 7px;
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  color: var(--af-text-2);
  line-height: 1.6;
}
.ks-branch { color: var(--af-text-3); flex-shrink: 0; }
.ks-index { color: var(--af-text-2); flex-shrink: 0; }
.ks-location { font-family: inherit; color: var(--af-text-2); }
/* 引用条目从 div 改为 button 后需重置浏览器默认外观；可点击项给出 hover 反馈 */
.ks-row {
  width: 100%;
  background: none;
  border: none;
  padding: 2px 6px;
  margin-left: -6px;
  border-radius: 6px;
  text-align: left;
  cursor: default;
}
.ks-row.is-link { cursor: pointer; }
.ks-row.is-link:hover {
  background: var(--af-hover, rgba(127, 127, 127, 0.1));
}
.ks-row.is-link:hover .ks-location { color: var(--af-primary); }
.ks-row:disabled { cursor: default; }
.ks-jump {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 12px;
  color: var(--af-text-3);
  opacity: 0;
  transition: opacity 0.15s ease;
}
.ks-row.is-link:hover .ks-jump { opacity: 1; color: var(--af-primary); }
.user .text-box {
  background: var(--af-primary-gradient);
  color: #fff;
  border-top-right-radius: 4px;
}

.msg-foot {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  color: var(--af-text-3);
}
.msg-foot-sep { opacity: 0.6; }
/* Token 用量：低调展示，鼠标悬停可看说明 */
.msg-usage {
  cursor: default;
  letter-spacing: 0.2px;
  opacity: 0.85;
}
/* 增量输出时的光标 */
.typing-caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: var(--af-primary);
  animation: caret-blink 0.9s steps(2, start) infinite;
}
@keyframes caret-blink {
  to { visibility: hidden; }
}

/* ===== 工作流实时进度 ===== */
.run-progress { max-width: 86%; }
.run-progress-box {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 10px 14px;
  border-radius: 12px;
  border-top-left-radius: 4px;
  background: var(--af-card);
  border: 1px dashed var(--af-border);
  font-size: 13px;
}
.run-progress.run-failed .run-progress-box { border-color: rgba(231, 76, 60, 0.45); }
.run-progress.run-success .run-progress-box { border-style: solid; border-color: rgba(46, 204, 113, 0.4); }
.run-progress-text { color: var(--af-text); word-break: break-word; }
.run-progress-text.error { color: #e74c3c; }
.run-step-name { color: var(--af-text-3); font-size: 12px; }
.run-hint { font-size: 11px; color: var(--af-text-3); }

/* 折叠开关：位于进度气泡左侧 */
.run-collapse-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--af-text-3);
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}
.run-collapse-btn:hover { color: var(--af-text); background: var(--af-hover); }

/* 步骤执行中的 loading（与知识库文档上传进度一致） */
.run-loading { color: var(--af-primary); font-size: 14px; flex-shrink: 0; }

/* ===== 业务任务卡片 ===== */
.task-card-list { display: flex; flex-direction: column; gap: 8px; max-width: 560px; }

/* —— 任务列表卡片（可点击选择）—— */
.task-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 12px 14px;
  text-align: left;
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  color: var(--af-text);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, transform 0.15s;
}
.task-card:hover:not(:disabled) {
  border-color: var(--af-primary);
  background: var(--af-card-soft);
  transform: translateY(-1px);
}
.task-card:disabled { cursor: not-allowed; opacity: 0.7; }
.task-card.selected { border-color: var(--af-primary); }

.task-card-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 9px;
  background: var(--af-primary-soft);
  color: var(--af-primary);
  font-size: 15px;
}
.task-card-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.task-card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.task-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--af-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-card-status {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  color: var(--af-text-2);
  background: var(--af-hover);
}
.task-card-status.collecting,
.task-card-status.waiting_input { color: var(--af-warning); background: var(--af-warning-soft); }
.task-card-status.waiting_confirmation,
.task-card-status.waiting_approval { color: var(--af-primary); background: var(--af-primary-soft); }
.task-card-status.completed,
.task-card-status.submitted { color: var(--af-success); background: rgba(46, 204, 113, 0.12); }
.task-card-status.cancelled { color: var(--af-text-3); }

.task-card-missing { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.task-missing-label { font-size: 11px; color: var(--af-text-3); }

/* 列表卡片摘要行：金额 · 笔数 · 类别 · 日期 */
.task-card-summary {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--af-text-3);
}
.task-sum-amount {
  font-size: 13px;
  font-weight: 600;
  color: var(--af-text);
  font-variant-numeric: tabular-nums;
}
.task-sum-meta { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.task-card-foot {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--af-primary);
}
.task-card-loading { font-size: 12px; }
.task-card-arrow { margin-left: auto; font-size: 12px; opacity: 0.55; transition: transform 0.15s, opacity 0.15s; }
.task-card:hover:not(:disabled) .task-card-arrow { transform: translateX(2px); opacity: 1; }

/* —— 单任务详情卡片 —— */
.task-detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
  max-width: 560px;
  padding: 16px;
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius);
}
.td-head { display: flex; align-items: flex-start; gap: 10px; }
.td-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 10px;
  background: var(--af-primary-soft);
  color: var(--af-primary);
  font-size: 17px;
}
.td-head-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.td-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.td-title { font-size: 15px; font-weight: 600; color: var(--af-text); }
.td-claim {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  color: var(--af-info);
  background: var(--af-info-soft);
}
/* 任务 UID：单行省略，点击复制 */
.td-uid {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--af-text-3);
  font-size: 11px;
  text-align: left;
  cursor: pointer;
  transition: color 0.15s;
}
.td-uid:hover { color: var(--af-text-2); }
.td-uid-label { flex-shrink: 0; }
.td-uid-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  letter-spacing: 0.2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.td-uid-icon { font-size: 11px; flex-shrink: 0; opacity: 0.7; }
.td-uid:hover .td-uid-icon { opacity: 1; }

/* 金额 / 明细数 / 创建时间：三栏等宽分格 */
.td-stats {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  gap: 1px;
  background: var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  overflow: hidden;
}
.td-stat { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; background: var(--af-card-soft); }
.td-stat-label { font-size: 11px; color: var(--af-text-3); }
.td-stat-value { font-size: 14px; font-weight: 600; color: var(--af-text); }
.td-stat-value.primary { font-size: 18px; color: var(--af-primary); letter-spacing: 0.3px; }
.td-stat-value.small { font-size: 12px; font-weight: 500; color: var(--af-text-2); }

/* 费用明细 */
.td-section { display: flex; flex-direction: column; gap: 8px; }
.td-section-head { display: flex; align-items: center; gap: 6px; }
.td-section-title { font-size: 12px; font-weight: 600; color: var(--af-text-2); }
.td-section-count {
  min-width: 18px;
  padding: 0 5px;
  height: 16px;
  line-height: 16px;
  border-radius: 8px;
  text-align: center;
  font-size: 10px;
  color: var(--af-text-2);
  background: var(--af-hover);
}
.td-empty {
  padding: 14px;
  border: 1px dashed var(--af-border);
  border-radius: var(--af-radius-sm);
  text-align: center;
  font-size: 12px;
  color: var(--af-text-3);
}
.td-items { display: flex; flex-direction: column; gap: 6px; }
.td-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
}
.td-item-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin-top: 1px;
  flex-shrink: 0;
  border-radius: 6px;
  background: var(--af-hover);
  color: var(--af-text-2);
  font-size: 10px;
  font-weight: 600;
}
.td-item-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.td-item-line { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.td-item-desc {
  font-size: 13px;
  color: var(--af-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.td-item-amount {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--af-text);
  font-variant-numeric: tabular-nums;
}
.td-item-amount.missing { font-size: 12px; color: var(--af-warning); }
.td-item-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 11px; color: var(--af-text-3); }
.td-chip { padding: 1px 7px; border-radius: 5px; background: var(--af-hover); color: var(--af-text-2); }
.td-chip.missing {
  color: var(--af-warning);
  background: var(--af-warning-soft);
  border: 1px dashed rgba(245, 166, 35, 0.4);
}
.td-item-date { font-variant-numeric: tabular-nums; }
.td-item-date.missing { color: var(--af-warning); font-weight: 600; }
.td-item-warn { color: var(--af-warning); }

/* 发票状态与上传入口 */
.td-invoice-ok {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--af-success);
  font-size: 11px;
}
.td-invoice-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 9px;
  border-radius: 6px;
  font-size: 11px;
  border: 1px dashed rgba(245, 166, 35, 0.45);
  background: var(--af-warning-soft);
  color: var(--af-warning);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.td-invoice-btn:hover:not(:disabled) { background: rgba(245, 166, 35, 0.22); }
.td-invoice-btn:disabled { opacity: 0.55; cursor: not-allowed; }
/* 已有发票时的补传入口：弱化为中性描边样式 */
.td-invoice-btn.ghost {
  border-style: solid;
  border-color: var(--af-border);
  background: transparent;
  color: var(--af-text-2);
}
.td-invoice-btn.ghost:hover:not(:disabled) {
  color: var(--af-text);
  border-color: var(--af-text-3);
  background: var(--af-hover);
}
/* 上传入口容器：透明 file input 铺满按钮，点击直接走原生选择器 */
.td-invoice-uploader {
  position: relative;
  display: inline-flex;
  vertical-align: middle;
}
.td-invoice-input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
  /* 16px：避免 iOS 聚焦时页面被放大 */
  font-size: 16px;
}

/* 待补充汇总 / 信息完整 */
.td-alert {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 12px;
  border-radius: var(--af-radius-sm);
  background: var(--af-warning-soft);
  border: 1px solid rgba(245, 166, 35, 0.25);
  color: var(--af-warning);
  font-size: 12px;
}
.td-ok {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 12px;
  border-radius: var(--af-radius-sm);
  background: var(--af-success-soft);
  color: var(--af-success);
  font-size: 12px;
}

.status-badge.idle { color: var(--af-text-3); background: var(--af-hover); }
.status-badge.failed { color: #e74c3c; background: rgba(231, 76, 60, 0.12); }

/* 表格样式 */
.table-box {
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 12px;
  padding: 16px;
  width: 100%;
  max-width: 600px;
  overflow-x: auto;
}
.table-title { font-weight: 600; margin-bottom: 12px; font-size: 14px; color: var(--af-text); }
.table-footer { margin-top: 12px; font-size: 12px; color: var(--af-text-3); }

/* 详情卡片样式 */
.detail-card {
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 12px;
  padding: 20px;
  width: 100%;
  max-width: 600px;
}
.detail-card .card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 20px; }
.card-icon { color: var(--af-primary); font-size: 18px; }
.card-title { font-weight: 600; font-size: 15px; flex: 1; color: var(--af-text); }
.card-body { display: flex; flex-direction: column; gap: 16px; }
.info-row { display: flex; gap: 24px; flex-wrap: wrap; }
.info-item { flex: 1; min-width: 120px; display: flex; flex-direction: column; gap: 4px; }
.info-item .label { font-size: 12px; color: var(--af-text-3); }
.info-item .value { font-size: 13px; color: var(--af-text); }
.info-item .value.amount { color: var(--af-primary); font-weight: 600; font-size: 16px; }
.card-footer { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--af-border-soft); }

.action-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
.suggest-btn {
  display: inline-flex; align-items: center; gap: 5px;
  background: var(--af-card);
  border: 1px solid var(--af-border);
  color: var(--af-text-2);
  border-radius: 18px;
  padding: 6px 14px;
  font-size: 12px;
  cursor: pointer;
  min-height: 32px;
}
.suggest-btn:hover { color: var(--af-primary); border-color: rgba(255, 92, 51, 0.4); }

/* 输入区域 */
.chat-input-area {
  padding: 16px 24px 12px;
  border-top: 1px solid var(--af-border-soft);
  flex-shrink: 0;
  position: relative; /* 「回到底部」按钮的定位基准 */
}
.input-container {
  border: 1px solid var(--af-border);
  border-radius: 14px;
  padding: 12px;
  background: var(--af-card);
}
.input-container:focus-within { border-color: rgba(255, 92, 51, 0.5); }
.custom-textarea :deep(.el-textarea__inner) {
  background: transparent;
  box-shadow: none;
  padding: 0;
  font-size: 14px;
  color: var(--af-text);
}
.input-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  margin-top: 10px;
  gap: 10px;
}
.send-btn {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--af-primary-gradient);
  border: none; border-radius: 10px;
  color: #fff; font-size: 13px; font-weight: 600;
  padding: 9px 18px;
  cursor: pointer;
  min-height: 40px;
}
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.input-disclaimer { text-align: center; color: var(--af-text-3); font-size: 10px; margin-top: 10px; }

/* ===== 右侧执行面板 ===== */
.execution-sidebar {
  width: 320px;
  flex-shrink: 0;
  background: #0d0d0d;
  border-left: 1px solid var(--af-border-soft);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.execution-tabs { height: 100%; display: flex; flex-direction: column; }
.execution-tabs :deep(.el-tabs__header) { padding: 0 12px; flex-shrink: 0; }
.execution-tabs :deep(.el-tabs__nav) { width: 100%; display: flex; }
.execution-tabs :deep(.el-tabs__item) { flex: 1; text-align: center; }
.execution-tabs :deep(.el-tabs__content) {
  padding: 16px;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.process-status {
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  padding: 14px;
  border-radius: 12px;
  margin-bottom: 18px;
}
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  color: var(--af-success);
  background: var(--af-success-soft);
  margin-bottom: 12px;
}
.run-row {
  display: flex; justify-content: space-between;
  font-size: 12px; padding: 5px 0;
}
.run-row span { color: var(--af-text-3); }
.run-row b { color: var(--af-text-2); font-weight: 500; }
.run-row b.ok { color: var(--af-success); }

.trace-title { color: var(--af-text); font-size: 13px; font-weight: 700; margin: 4px 0 14px; }

.step-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.step-title { font-weight: 600; font-size: 13px; color: var(--af-text); }
.step-state-tag { margin-left: 6px; transform: scale(0.86); transform-origin: left center; }
.step-time { font-size: 11px; color: var(--af-text-3); }
.step-desc { font-size: 11px; color: var(--af-text-3); line-height: 1.6; }

.resource-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.res-card {
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 12px;
  padding: 13px;
  display: flex; flex-direction: column; gap: 5px;
}
.res-label { color: var(--af-text-3); font-size: 11px; }
.res-value { color: var(--af-text); font-size: 20px; font-weight: 800; }
.res-value i { font-size: 11px; color: var(--af-success); font-style: normal; }
.res-value.green { color: var(--af-success); }
.res-sub { color: var(--af-text-3); font-size: 10px; }

.empty-state { text-align: center; color: var(--af-text-3); font-size: 12px; padding: 40px 0; }

/* ===== 相关任务面板 ===== */
.task-panel-loading {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  color: var(--af-text-3); font-size: 12px; padding: 40px 0;
}
.task-panel-list { display: flex; flex-direction: column; gap: 8px; }
.task-panel-item {
  width: 100%;
  text-align: left;
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 10px;
  padding: 10px 12px;
  display: flex; flex-direction: column; gap: 5px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  font-family: inherit;
}
.task-panel-item:hover { border-color: var(--af-border); background: var(--af-card-soft); }
.task-panel-item.active { border-color: var(--af-primary); }
.task-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.task-panel-title { color: var(--af-text); font-size: 12px; font-weight: 500; }
.task-panel-status {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--af-text-3);
  padding: 1px 6px;
  border-radius: 6px;
  border: 1px solid var(--af-border);
}
.task-panel-status.completed { color: var(--af-success); border-color: currentColor; }
.task-panel-status.collecting,
.task-panel-status.waiting_confirmation { color: var(--af-warning); border-color: currentColor; }
.task-panel-status.failed { color: var(--af-danger); border-color: currentColor; }
.task-panel-meta {
  display: flex; align-items: center; gap: 4px; flex-wrap: wrap;
  color: var(--af-text-2); font-size: 11px;
}
.task-panel-meta .sep { color: var(--af-text-3); }
.task-panel-claim { color: var(--af-text-2); font-family: var(--af-font-mono, ui-monospace, monospace); }
.task-panel-missing { color: var(--af-warning); font-size: 11px; }

.info-list { display: flex; flex-direction: column; gap: 16px; }
.info-item { display: flex; justify-content: space-between; align-items: center; font-size: 12px; }
.info-item .label { color: var(--af-text-3); }
.info-item .value { color: var(--af-text-2); }

/* 移动端抽屉内的会话列表 */
.drawer-sessions { height: 100%; display: flex; flex-direction: column; background: #0d0d0d; }
.drawer-foot {
  margin-top: auto;
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom));
  border-top: 1px solid var(--af-border-soft);
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--af-text-3);
  font-size: 11px;
}
.drawer-online { display: inline-flex; align-items: center; gap: 7px; }

/* ===== 报销记录列表卡片（extra_data.ui_type = expense_claim_list） ===== */
.claim-card {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 560px;
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: 12px;
  overflow: hidden;
}
.claim-card-head {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--af-border-soft);
}
.claim-card-title {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--af-text); font-size: 13px; font-weight: 700;
}
.claim-card-title .el-icon { color: var(--af-primary); }
.claim-card-count {
  color: var(--af-text-3); font-size: 11px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}

.claim-row {
  display: flex; align-items: center; gap: 10px;
  width: 100%;
  padding: 12px 14px;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--af-border-soft);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s;
}
.claim-row:hover { background: var(--af-hover); }
.claim-row:hover .claim-row-arrow { color: var(--af-primary); transform: translateX(2px); }
.claim-row-main { flex: 1; min-width: 0; }
.claim-row-top { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; min-width: 0; }
.claim-row-no {
  color: var(--af-info); font-size: 11px; font-weight: 500;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  letter-spacing: -0.2px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.claim-status {
  flex-shrink: 0;
  font-size: 10px; font-weight: 500;
  padding: 2px 8px;
  border-radius: 9999px;
  border: 1px solid transparent;
  white-space: nowrap;
}
.claim-status.st-pending { color: var(--af-warning); background: var(--af-warning-soft); border-color: rgba(245, 166, 35, 0.3); }
.claim-status.st-ok { color: var(--af-success); background: var(--af-success-soft); border-color: rgba(46, 204, 113, 0.3); }
.claim-status.st-fail { color: var(--af-danger); background: var(--af-danger-soft); border-color: rgba(255, 77, 79, 0.3); }
.claim-status.st-processing { color: var(--af-info); background: var(--af-info-soft); border-color: rgba(77, 141, 255, 0.3); }
.claim-status.st-draft { color: var(--af-text-3); background: var(--af-hover); border-color: var(--af-border-soft); }

.claim-row-title {
  color: var(--af-text); font-size: 13px; font-weight: 600;
  margin-bottom: 4px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.claim-row-meta {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  color: var(--af-text-3); font-size: 11px;
}
.claim-row-amount {
  color: var(--af-text); font-size: 13px; font-weight: 700;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.claim-row-sep { color: var(--af-text-3); }
.claim-row-cats { white-space: nowrap; }
.claim-row-desc {
  max-width: 240px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.claim-row-time {
  color: var(--af-text-3); font-size: 10px; margin-top: 4px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.claim-row-arrow {
  color: var(--af-text-3); font-size: 14px;
  flex-shrink: 0;
  transition: all 0.15s;
}

.claim-empty {
  padding: 24px 14px;
  text-align: center;
  color: var(--af-text-3);
  font-size: 12px;
}

.claim-pager {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 10px 14px 6px;
}
.claim-pager-info {
  color: var(--af-text-3); font-size: 11px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.claim-pager-hint { padding: 0 14px 10px; color: var(--af-text-3); font-size: 10px; }

/* ===== 报销单详情卡片 ===== */
.claim-detail-card { max-width: 100%; }
.cd-head { padding: 12px 14px 0; display: flex; flex-direction: column; gap: 6px; }
.cd-no {
  color: var(--af-primary); font-size: 12px; font-weight: 600;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  letter-spacing: 0.02em;
}
.cd-title { color: var(--af-text); font-size: 13px; font-weight: 600; }
.cd-desc { color: var(--af-text-3); font-size: 11px; line-height: 1.6; }
.cd-summary {
  display: flex; align-items: stretch; gap: 16px;
  margin: 10px 14px 0; padding: 10px 12px;
  border-radius: 10px;
  background: var(--af-hover);
  border: 1px solid var(--af-border-soft);
}
.cd-amount { display: flex; flex-direction: column; justify-content: center; gap: 4px; flex-shrink: 0; }
.cd-amount-label { color: var(--af-text-3); font-size: 10px; }
.cd-amount-value {
  color: var(--af-primary); font-size: 18px; font-weight: 700;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.cd-summary-meta { flex: 1; display: flex; flex-direction: column; justify-content: center; gap: 6px; min-width: 0; }
.cd-meta-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.cd-meta-label { color: var(--af-text-3); font-size: 11px; flex-shrink: 0; }
.cd-meta-value {
  color: var(--af-text-2); font-size: 11px; text-align: right;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cd-section { border-top: 1px solid var(--af-border-soft); margin-top: 10px; padding: 10px 14px 4px; }
.cd-section-title {
  display: flex; align-items: center; gap: 6px;
  color: var(--af-text-2); font-size: 11px; font-weight: 600;
  margin-bottom: 6px;
}
.cd-section-count { color: var(--af-text-3); font-weight: 400; }
.cd-items { display: flex; flex-direction: column; }
.cd-item {
  display: grid; grid-template-columns: auto 1fr auto auto;
  align-items: center; gap: 10px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--af-border-soft);
  font-size: 11px;
}
.cd-item:last-child { border-bottom: none; }
.cd-item-cat { color: var(--af-text-2); flex-shrink: 0; }
.cd-item-desc { color: var(--af-text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cd-item-date {
  color: var(--af-text-3); flex-shrink: 0;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.cd-item-amount {
  color: var(--af-text); font-weight: 600; flex-shrink: 0; text-align: right;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.cd-empty { color: var(--af-text-3); font-size: 11px; padding: 2px 0 6px; }
.cd-pr { display: flex; flex-direction: column; gap: 6px; }
.cd-pr-head { display: flex; align-items: center; gap: 8px; }
.cd-pr-risk {
  color: var(--af-text-3); font-size: 10px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  text-transform: uppercase;
}
.cd-pr-summary { color: var(--af-text-2); font-size: 11px; line-height: 1.7; }
.cd-approvals { display: flex; flex-direction: column; }
.cd-approval { padding: 6px 0; border-bottom: 1px dashed var(--af-border-soft); }
.cd-approval:last-child { border-bottom: none; }
.cd-approval-head { display: flex; align-items: center; gap: 8px; }
.cd-approval-approver { color: var(--af-text-2); font-size: 11px; }
.cd-approval-time {
  margin-left: auto; color: var(--af-text-3); font-size: 10px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.cd-approval-comment {
  margin-top: 5px; padding: 6px 8px;
  border-radius: 6px; background: var(--af-hover);
  color: var(--af-text-3); font-size: 11px; line-height: 1.6;
}
.cd-atts { display: flex; flex-wrap: wrap; gap: 6px; padding-bottom: 4px; }
.cd-att {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 8px; border-radius: 6px;
  border: 1px solid var(--af-border-soft); background: var(--af-hover);
  color: var(--af-text-2); font-size: 11px;
  max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cd-att .el-icon { font-size: 12px; color: var(--af-text-3); flex-shrink: 0; }
.cd-footer { border-top: 1px solid var(--af-border-soft); margin-top: 10px; padding: 8px 14px 10px; }
.cd-open {
  width: 100%; display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 7px 0; border-radius: 8px;
  border: 1px solid var(--af-border-soft); background: var(--af-elevated, var(--af-hover));
  color: var(--af-text-2); font-size: 12px; cursor: pointer;
  transition: all 0.15s;
}
.cd-open:hover { color: var(--af-primary); border-color: rgba(255, 92, 51, 0.4); background: var(--af-primary-soft); }

/* ===== 报销审批进度卡片 ===== */
.pg-head { flex-direction: row; align-items: center; justify-content: space-between; gap: 12px; }
.pg-head-left { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.pg-head-amount {
  color: var(--af-primary); font-size: 15px; font-weight: 700; flex-shrink: 0;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.cd-timeline { position: relative; margin: 12px 14px 0; padding: 0 0 12px 4px; }
.cd-tl-node {
  position: relative;
  display: flex; align-items: flex-start; gap: 12px;
  padding: 0 0 14px 0;
}
.cd-tl-node:last-child { padding-bottom: 0; }
/* 左侧连线：贯穿到下一个节点 */
.cd-tl-node::before {
  content: '';
  position: absolute; left: 7px; top: 18px; bottom: -2px;
  width: 1px; background: var(--af-border-soft);
}
.cd-tl-node:last-child::before { display: none; }
.cd-tl-dot {
  position: relative; z-index: 1;
  width: 15px; height: 15px; border-radius: 50%;
  flex-shrink: 0; margin-top: 1px;
  border: 1px solid transparent;
}
.cd-tl-dot::after {
  content: '';
  position: absolute; inset: 4px; border-radius: 50%;
}
.cd-tl-dot.tl-ok { border-color: rgba(46, 204, 113, 0.4); }
.cd-tl-dot.tl-ok::after { background: var(--af-success); }
.cd-tl-dot.tl-fail { border-color: rgba(255, 77, 79, 0.4); }
.cd-tl-dot.tl-fail::after { background: var(--af-danger); }
.cd-tl-dot.tl-draft::after { background: var(--af-text-3); opacity: 0.5; }
.cd-tl-dot.tl-wait {
  border-color: rgba(255, 92, 51, 0.45);
  background: var(--af-primary-soft);
}
.cd-tl-dot.tl-wait::after { background: var(--af-primary); animation: tl-pulse 1.6s ease-in-out infinite; }
@keyframes tl-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.cd-tl-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.cd-tl-row { display: flex; align-items: center; gap: 8px; min-height: 17px; }
.cd-tl-label { color: var(--af-text-2); font-size: 12px; font-weight: 600; }
.cd-tl-approver { color: var(--af-text-2); font-size: 11px; }
.cd-tl-time {
  margin-left: auto; color: var(--af-text-3); font-size: 10px; flex-shrink: 0;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.cd-tl-wait-label { color: var(--af-primary); }
.cd-tl-hint { color: var(--af-text-3); font-size: 11px; }
/* 进度卡里复用详情卡的附言引用块，左对齐时间线 */
.cd-tl-body .cd-approval-comment { margin-top: 2px; }
.cd-tl-summary {
  padding: 4px 0 0 27px;
  color: var(--af-text-3); font-size: 10px;
}

/* ===== AI 预审报告卡片 ===== */
.pr-banner {
  margin: 10px 14px 0; padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--af-border-soft);
  background: var(--af-hover);
  display: flex; flex-direction: column; gap: 8px;
}
.pr-banner.st-fail { background: var(--af-danger-soft); border-color: rgba(255, 77, 79, 0.25); }
.pr-banner.st-ok { background: var(--af-success-soft); border-color: rgba(46, 204, 113, 0.25); }
.pr-banner.st-pending { background: var(--af-warning-soft); border-color: rgba(245, 166, 35, 0.25); }
.pr-banner-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.pr-duration {
  margin-left: auto; color: var(--af-text-3); font-size: 10px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.pr-banner-summary { color: var(--af-text-2); font-size: 12px; line-height: 1.7; }
.pr-problems { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.pr-problems li {
  display: flex; align-items: flex-start; gap: 8px;
  color: var(--af-text-2); font-size: 11px; line-height: 1.6;
}
.pr-problems li .el-icon { color: var(--af-danger); font-size: 13px; margin-top: 2px; flex-shrink: 0; }
.pr-evidence {
  padding: 8px 10px; border-radius: 8px;
  background: var(--af-hover); border-left: 2px solid var(--af-border-strong, var(--af-text-3));
  color: var(--af-text-2); font-size: 11px; line-height: 1.7;
}
.pr-doc {
  display: inline-flex; align-items: center; gap: 6px;
  margin-top: 8px; font-size: 11px;
}
.pr-doc .el-icon { font-size: 14px; }
.pr-doc.pr-doc-ok { color: var(--af-success); }
.pr-doc.pr-doc-bad { color: var(--af-danger); }
.pr-extracted { display: flex; flex-direction: column; gap: 6px; }
.pr-extracted-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 5px 0;
  border-bottom: 1px dashed var(--af-border-soft);
  font-size: 11px;
}
.pr-extracted-row:last-child { border-bottom: none; }
.pr-extracted-label { color: var(--af-text-3); flex-shrink: 0; }
.pr-extracted-value {
  color: var(--af-text-2); text-align: right; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}

/* ===== 报销统计卡片 ===== */
.st-overview {
  display: flex; flex-wrap: wrap; gap: 10px;
  margin: 10px 14px 0;
}
.st-amount-box {
  flex: 1; min-width: 140px;
  display: flex; flex-direction: column; gap: 4px;
  padding: 10px 12px; border-radius: 10px;
  background: var(--af-hover);
  border: 1px solid var(--af-border-soft);
}
.st-amount-label { color: var(--af-text-3); font-size: 10px; }
.st-amount-value {
  color: var(--af-primary); font-size: 17px; font-weight: 700;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.st-amount-sub { color: var(--af-text-3); font-size: 10px; }
.st-bar {
  display: flex; height: 8px; border-radius: 4px; overflow: hidden;
  background: var(--af-hover);
}
.st-bar-seg { display: block; height: 100%; }
.st-bar-seg.bar-ok { background: var(--af-success); }
.st-bar-seg.bar-pending { background: var(--af-warning); }
.st-bar-seg.bar-fail { background: var(--af-danger); }
.st-bar-seg.bar-processing { background: var(--af-info); }
.st-bar-seg.bar-draft { background: var(--af-text-3); opacity: 0.5; }
.st-legend { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }
.st-legend-item { display: inline-flex; align-items: center; gap: 5px; color: var(--af-text-3); font-size: 11px; }
.st-legend-item b { color: var(--af-text-2); font-weight: 600; }
.st-legend-dot { width: 8px; height: 8px; border-radius: 2px; }
.st-legend-dot.bar-ok { background: var(--af-success); }
.st-legend-dot.bar-pending { background: var(--af-warning); }
.st-legend-dot.bar-fail { background: var(--af-danger); }
.st-legend-dot.bar-processing { background: var(--af-info); }
.st-legend-dot.bar-draft { background: var(--af-text-3); opacity: 0.5; }
.st-cats { display: flex; flex-direction: column; gap: 10px; }
.st-cat { display: flex; flex-direction: column; gap: 5px; }
.st-cat-head {
  display: grid; grid-template-columns: 1fr auto auto;
  align-items: baseline; gap: 10px;
}
.st-cat-name { color: var(--af-text-2); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.st-cat-count { color: var(--af-text-3); font-size: 10px; flex-shrink: 0; }
.st-cat-amount {
  color: var(--af-text); font-size: 11px; font-weight: 600; flex-shrink: 0;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.st-cat-bar {
  height: 4px; border-radius: 2px; overflow: hidden;
  background: var(--af-hover);
}
.st-cat-bar span {
  display: block; height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, rgba(255, 92, 51, 0.45), var(--af-primary));
}

/* ===== 响应式 ===== */
@media (max-width: 1100px) {
  .execution-sidebar { display: none; }
}
@media (max-width: 768px) {
  .chat-sessions-sidebar { display: none; }
  /* 顶栏整条去掉，会话入口悬浮在左上角，标题信息由抽屉承载 */
  .chat-header { display: none; }
  .mobile-sessions-fab { display: inline-flex; }
  /* 在线状态在窄屏上占空间，收进会话抽屉底部展示 */
  .chat-tag { display: none; }
  /* 顶部多留一点空间，避免首条消息被悬浮的会话按钮压住 */
  .chat-messages { padding: 12px 14px; gap: 16px; padding-top: 44px; }
  .message-wrapper { max-width: 100%; }
  /* 移动端输入区压缩：单行起、小按钮，把纵向空间让给消息列表
     注意：字号必须 >= 16px，否则 iOS Safari 聚焦时会自动放大整个页面 */
  .chat-input-area { padding: 8px 12px 6px; }
  .input-container { padding: 8px 10px; border-radius: 12px; }
  .custom-textarea :deep(.el-textarea__inner) { font-size: 16px; line-height: 1.5; }
  .input-toolbar { margin-top: 5px; }
  .send-btn { min-height: 32px; padding: 5px 13px; font-size: 12px; border-radius: 8px; }
  .input-disclaimer { display: none; }
}
</style>
