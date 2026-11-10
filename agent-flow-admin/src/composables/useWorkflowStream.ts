import { onBeforeUnmount, ref } from 'vue'
import {
  getWorkflowRunStatusApi,
  watchWorkflowEvents,
  type RunMetrics,
  type WorkflowEvent,
  type RunStepStatus,
  type WorkflowRunStatus
} from '@/api/chat'

/** 终态：收到后不再需要保持连接 */
const TERMINAL_STATUSES: WorkflowRunStatus[] = ['success', 'failed', 'cancelled']

export const isTerminalStatus = (status: WorkflowRunStatus): boolean =>
  TERMINAL_STATUSES.includes(status)

/** 右侧执行时间线中的步骤节点 */
export interface WorkflowStepView {
  /** 步骤稳定标识（来自 step_key，缺失时用 step_name 兜底） */
  stepKey: string
  stepName: string
  status: RunStepStatus | WorkflowRunStatus
  message: string
  time?: string
}

/** 会话内当前工作流的展示状态 */
export interface WorkflowProgress {
  conversationUid: string
  runUid: string
  status: WorkflowRunStatus
  /** 当前进度提示（来自 SSE 的 message 字段） */
  message: string
  /** 当前执行步骤名（来自 step_started 事件） */
  stepName: string
  /** 按 step_key 聚合的执行步骤，供右侧时间线展示 */
  steps: WorkflowStepView[]
  /** 失败原因（来自 run_failed 事件或状态查询） */
  errorMessage: string
  /** 本次运行的起始时间（服务端事件时间；缺失时由页面用本地时间兜底） */
  startedAt: string | null
  /** 终态耗时（毫秒），运行中为 null */
  durationMs: number | null
  /** 本次运行实际使用的模型 */
  model: string | null
  /** 本次运行的真实指标（调用次数 / 检索命中 / tokens） */
  metrics: RunMetrics | null
  /** SSE 多次重连仍不可用；只表示进度不可用，不代表工作流失败 */
  connectionLost: boolean
}

interface UseWorkflowStreamOptions {
  /** 每收到一条有效事件时回调 */
  onUpdate?: (progress: WorkflowProgress, event: WorkflowEvent) => void
  /** 工作流进入终态（成功/失败/取消）时回调 */
  onTerminal?: (progress: WorkflowProgress) => void
}

/** 事件去重窗口大小（防止长时间运行导致集合无限增长） */
const MAX_SEEN_EVENTS = 200

/**
 * 统一管理工作流的 SSE 连接：
 * - 按 event_uid 去重，重连后重复事件不会重复插入消息/步骤
 * - 步骤按 step_key 聚合，progress 只更新已有节点
 * - 断线不直接判定失败，先查询真实状态再决定是否重连
 * - 页面卸载时自动清理
 */
export function useWorkflowStream(options: UseWorkflowStreamOptions = {}) {
  const progress = ref<WorkflowProgress | null>(null)
  const streaming = ref(false)

  let handle: { abort: () => void } | null = null
  let activeRunUid: string | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectAttempts = 0
  let disposed = false
  /** 已处理的 event_uid，用于客户端去重 */
  let seenEventUids = new Set<string>()

  const MAX_RECONNECT = 3
  /** 快速重试用尽后的慢速自愈间隔 */
  const SLOW_RETRY_MS = 10000

  const clearReconnectTimer = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  /** 关闭连接（不清空展示状态） */
  const closeConnection = () => {
    clearReconnectTimer()
    disposed = true
    handle?.abort()
    handle = null
    streaming.value = false
  }

  /** 进入终态：关闭连接并通知页面 */
  const finish = (finalProgress: WorkflowProgress) => {
    closeConnection()
    activeRunUid = null
    progress.value = finalProgress
    options.onTerminal?.(finalProgress)
  }

  /**
   * 断线处理：先查询后端真实状态，避免漏掉终止事件后一直停留在执行中。
   * 仍在执行时按上限重连；查询失败也重试，超过上限标记连接中断（不标记失败）。
   */
  const reconcile = async (conversationUid: string, runUid: string) => {
    if (disposed) return

    try {
      const res = await getWorkflowRunStatusApi(conversationUid, runUid)
      const data = res?.data
      if (!data || data.run_uid !== runUid) {
        throw new Error('工作流状态查询返回异常')
      }

      const next: WorkflowProgress = {
        conversationUid,
        runUid,
        status: data.status,
        message: progress.value?.message ?? '',
        stepName: progress.value?.stepName ?? '',
        steps: progress.value?.steps ?? [],
        errorMessage: data.error_message ?? '',
        startedAt: data.started_at ?? progress.value?.startedAt ?? null,
        durationMs: data.duration_ms ?? progress.value?.durationMs ?? null,
        model: data.model_name ?? progress.value?.model ?? null,
        metrics: progress.value?.metrics ?? null,
        connectionLost: false
      }

      if (isTerminalStatus(data.status)) {
        finish(next)
        return
      }
    } catch {
      // 状态查询失败时按普通断线处理，继续重试
    }

    if (disposed) return

    if (reconnectAttempts >= MAX_RECONNECT) {
      // 快速重试用尽：标记进度连接中断，但进入慢速自愈循环——
      // 只要工作流还没有终态，就每 10s 重新建连/核对状态，直到拿到终态或会话切换。
      closeConnection()
      if (progress.value && activeRunUid === runUid) {
        progress.value = { ...progress.value, connectionLost: true }
      }
      reconnectAttempts = 0
      clearReconnectTimer()
      reconnectTimer = setTimeout(() => {
        if (disposed || activeRunUid !== runUid) return
        connect(conversationUid, runUid)
      }, SLOW_RETRY_MS)
      return
    }

    reconnectAttempts += 1
    clearReconnectTimer()
    reconnectTimer = setTimeout(() => {
      if (disposed) return
      connect(conversationUid, runUid)
    }, 1000 * reconnectAttempts)
  }

  /**
   * 按 step_key 合并步骤：存在则更新，不存在则追加。
   * 同一步骤的多次 progress 事件只更新原节点，不会重复新增。
   * 展示名优先级：display_name > step_name > step_key。
   */
  const mergeStep = (
    steps: WorkflowStepView[],
    payload: WorkflowEvent,
    fallbackKey: string
  ): WorkflowStepView[] => {
    const stepKey = payload.step_key || payload.step_name || fallbackKey
    const displayName = payload.display_name || payload.step_name || stepKey
    const index = steps.findIndex((item) => item.stepKey === stepKey)
    const base: WorkflowStepView =
      index >= 0
        ? steps[index]
        : {
            stepKey,
            stepName: displayName,
            status: 'pending',
            message: ''
          }

    const merged: WorkflowStepView = {
      ...base,
      stepName: payload.display_name || payload.step_name || base.stepName,
      // 步骤维度才采信 status，避免把工作流状态写到步骤上
      status:
        payload.scope === 'step' && payload.status
          ? (payload.status as RunStepStatus)
          : base.status,
      message: payload.message ?? base.message,
      time: payload.time ?? base.time
    }

    if (index >= 0) {
      const next = [...steps]
      next[index] = merged
      return next
    }
    return [...steps, merged]
  }

  /** 工作流进入终态时，把仍在执行的步骤收敛到对应结果，避免时间线一直转圈 */
  const sealSteps = (
    steps: WorkflowStepView[],
    status: WorkflowRunStatus
  ): WorkflowStepView[] => {
    const target: RunStepStatus =
      status === 'success' ? 'success' : status === 'cancelled' ? 'skipped' : 'failed'
    return steps.map((step) =>
      step.status === 'running' || step.status === 'pending'
        ? { ...step, status: target }
        : step
    )
  }

  /** 建立（或重建）SSE 连接 */
  function connect(conversationUid: string, runUid: string) {
    disposed = false
    activeRunUid = runUid
    streaming.value = true

    handle = watchWorkflowEvents(conversationUid, runUid, {
      onEvent: (name, payload) => {
        // 旧连接/旧会话的事件直接丢弃
        if (activeRunUid !== runUid || disposed) return
        if (!payload) return

        // 按 event_uid 去重（重连后快照/重复推送不会重复处理）
        if (payload.event_uid) {
          if (seenEventUids.has(payload.event_uid)) return
          seenEventUids.add(payload.event_uid)
          if (seenEventUids.size > MAX_SEEN_EVENTS) {
            const oldest = seenEventUids.values().next().value
            if (oldest) seenEventUids.delete(oldest)
          }
        }

        reconnectAttempts = 0

        const current: WorkflowProgress = progress.value ?? {
          conversationUid,
          runUid,
          status: 'pending',
          message: '',
          stepName: '',
          steps: [],
          errorMessage: '',
          startedAt: null,
          durationMs: null,
          model: null,
          metrics: null,
          connectionLost: false
        }
        const next: WorkflowProgress = { ...current, connectionLost: false }

        /** 合并后端下发的真实运行指标 */
        const applyMetrics = (metrics?: RunMetrics | null) => {
          if (!metrics) return
          next.metrics = metrics
          if (metrics.engine) next.model = metrics.engine
          if (typeof metrics.duration_ms === 'number') {
            next.durationMs = metrics.duration_ms
          }
        }

        switch (name) {
          case 'run_snapshot':
            // 快照只带 run_uid + status（无 event/scope 字段）
            if (payload.status) next.status = payload.status as WorkflowRunStatus
            break
          case 'run_started':
            next.status = 'running'
            next.message = payload.message ?? next.message
            // 服务端事件时间即本次运行的起点，用于运行中实时计时
            next.startedAt = payload.time ?? next.startedAt ?? null
            break
          case 'step_started':
            next.steps = mergeStep(next.steps, payload, payload.step_key || '__step')
            next.stepName = payload.display_name || payload.step_name || next.stepName
            next.message = payload.message ?? next.message
            break
          case 'progress':
            // progress 不是聊天正文，只更新已有步骤或整体进度提示
            if (payload.step_key || payload.step_name) {
              next.steps = mergeStep(next.steps, payload, payload.step_key || '__step')
            }
            next.message = payload.message ?? next.message
            break
          case 'content_delta':
            // 增量正文由页面追加展示，这里只保证事件被透传，不改工作流状态
            break
          case 'assistant_message':
            // 最终回复内容由页面消费，运行状态仍以 run_completed 为准
            // 卡片数据里带了 run_metrics 时先记下来，作为指标兜底
            if (payload.extra_data) {
              const raw = (payload.extra_data as { run_metrics?: RunMetrics })
                .run_metrics
              applyMetrics(raw ?? null)
            }
            break
          case 'run_completed':
            next.status = 'success'
            next.steps = sealSteps(next.steps, 'success')
            next.message = payload.message ?? next.message
            next.startedAt = next.startedAt ?? payload.time ?? null
            applyMetrics(payload.metrics)
            break
          case 'run_failed':
            next.status = 'failed'
            next.steps = sealSteps(next.steps, 'failed')
            next.errorMessage = payload.error_message ?? payload.message ?? ''
            next.startedAt = next.startedAt ?? payload.time ?? null
            applyMetrics(payload.metrics)
            break
          case 'run_cancelled':
            next.status = 'cancelled'
            next.steps = sealSteps(next.steps, 'cancelled')
            next.message = payload.message ?? next.message
            next.startedAt = next.startedAt ?? payload.time ?? null
            break
          default:
            // 未知事件忽略，避免影响现有状态
            return
        }

        progress.value = next
        options.onUpdate?.(next, { ...payload, event: name })

        if (isTerminalStatus(next.status)) {
          finish(next)
        }
      },
      onClose: () => {
        // 服务端在推送终态后会主动关闭连接，此时已由 finish 处理
        if (disposed || activeRunUid !== runUid) return
        void reconcile(conversationUid, runUid)
      },
      onError: () => {
        // 连接异常不等于工作流失败
        if (disposed || activeRunUid !== runUid) return
        void reconcile(conversationUid, runUid)
      }
    })
  }

  /** 订阅指定工作流；同一个 run 重复调用不会重复建连 */
  const start = (
    conversationUid: string,
    runUid: string,
    initialStatus: WorkflowRunStatus = 'pending'
  ) => {
    if (activeRunUid === runUid && handle) return

    closeConnection()
    reconnectAttempts = 0
    seenEventUids = new Set<string>()
    progress.value = {
      conversationUid,
      runUid,
      status: initialStatus,
      message: '',
      stepName: '',
      steps: [],
      errorMessage: '',
      // 本地兜底起点，收到 run_started 后以服务端时间为准
      startedAt: new Date().toISOString(),
      durationMs: null,
      model: null,
      metrics: null,
      connectionLost: false
    }
    connect(conversationUid, runUid)

    // 用服务端记录校正起点/模型/耗时：刷新页面后接续既有运行时也能看到真实数据。
    void getWorkflowRunStatusApi(conversationUid, runUid)
      .then((res) => {
        const data = res?.data
        if (!data || activeRunUid !== runUid || disposed) return
        const current = progress.value
        if (!current || current.runUid !== runUid) return
        progress.value = {
          ...current,
          startedAt: data.started_at ?? current.startedAt,
          durationMs: data.duration_ms ?? current.durationMs,
          model: data.model_name ?? current.model
        }
      })
      .catch(() => {
        // 状态查询失败不影响 SSE 主流程
      })
  }

  /** 停止订阅并清空展示状态（切换会话、页面卸载时使用） */
  const stop = () => {
    closeConnection()
    activeRunUid = null
    reconnectAttempts = 0
    seenEventUids = new Set<string>()
    progress.value = null
  }

  onBeforeUnmount(stop)

  return { progress, streaming, start, stop }
}
