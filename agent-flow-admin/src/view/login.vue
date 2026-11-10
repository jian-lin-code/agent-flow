<template>
  <div class="login-page">
    <!-- 顶部品牌栏 -->
    <header class="login-header">
      <div class="brand">
        <div class="brand-logo">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3" />
            <circle cx="5" cy="5" r="2" /><circle cx="19" cy="5" r="2" />
            <circle cx="5" cy="19" r="2" /><circle cx="19" cy="19" r="2" />
            <path d="M7 7l3 3M17 7l-3 3M7 17l3-3M17 17l-3-3" />
          </svg>
        </div>
        <div class="brand-text">
          <span class="brand-name">AgentFlow</span>
          <span class="brand-by">by @nexuslab</span>
        </div>
        <span class="brand-tag">v3.4<br />ENTERPRISE</span>
      </div>
      <div class="header-right">
        <span class="header-pill"><span class="dot green" />{{ $t('login.readyCluster') }}</span>
        <span class="header-pill">{{ $t('login.docs') }}</span>
      </div>
    </header>

    <div class="login-body">
      <!-- ===== 左侧品牌/介绍区（PC） ===== -->
      <section class="hero-side">
        <div class="hero-badge"><span class="dot" /> {{ $t('login.heroBadge') }}</div>
        <h1 class="hero-title">
          {{ $t('login.heroTitle1') }}<br />
          <span class="gradient-text">{{ $t('login.heroTitle2') }}</span>
        </h1>
        <p class="hero-desc">
          {{ $t('login.heroDesc') }}
        </p>

        <div class="hero-card">
          <div class="hero-card-head">
            <span><span class="dot green" /> {{ $t('login.heroCardHead') }}</span>
            <span class="coord-tag">{{ $t('login.coordTag') }}</span>
          </div>
          <div class="hero-stats">
            <div class="hero-stat">
              <div class="hs-label">{{ $t('login.stat1Label') }}</div>
              <div class="hs-value orange">85% <span>{{ $t('login.stat1Sub') }}</span></div>
            </div>
            <div class="hero-stat">
              <div class="hs-label">{{ $t('login.stat2Label') }}</div>
              <div class="hs-value green">99.8% <span>{{ $t('login.stat2Sub') }}</span></div>
            </div>
            <div class="hero-stat">
              <div class="hs-label">{{ $t('login.stat3Label') }}</div>
              <div class="hs-value">100% <span>{{ $t('login.stat3Sub') }}</span></div>
            </div>
          </div>
          <div class="hero-pipeline">
            <div class="pipe-item">
              <span class="pipe-num">1</span>
              <div class="pipe-text">
                <b>{{ $t('login.pipe1Title') }}</b>
                <i>{{ $t('login.pipe1Desc') }}</i>
              </div>
              <span class="pipe-state green"><el-icon><Check /></el-icon> {{ $t('login.pipe1State') }}</span>
            </div>
            <div class="pipe-item">
              <span class="pipe-num">2</span>
              <div class="pipe-text">
                <b>{{ $t('login.pipe2Title') }}</b>
                <i>{{ $t('login.pipe2Desc') }}</i>
              </div>
              <span class="pipe-state green"><el-icon><Check /></el-icon> {{ $t('login.pipe2State') }}</span>
            </div>
            <div class="pipe-item">
              <span class="pipe-num">3</span>
              <div class="pipe-text">
                <b>{{ $t('login.pipe3Title') }}</b>
                <i>{{ $t('login.pipe3Desc') }}</i>
              </div>
              <span class="pipe-state orange">{{ $t('login.pipe3State') }}</span>
            </div>
          </div>
          <div class="hero-foot">
            <span><el-icon><Lock /></el-icon> {{ $t('login.footEncrypt') }}</span>
            <span>{{ $t('login.footCount') }}</span>
          </div>
        </div>
      </section>

      <!-- ===== 右侧登录卡片 ===== -->
      <section class="form-side">
        <div class="login-card">
          <div class="login-head">
            <div>
              <h2>{{ $t('login.welcome') }}</h2>
              <p>{{ $t('login.welcomeDesc') }}</p>
            </div>
            <span class="card-tag">{{ $t('login.cardTag') }}</span>
          </div>

          <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" size="large" @submit.prevent>
            <div class="field-label">{{ $t('login.labelAccount') }}</div>
            <el-form-item prop="username">
              <el-input v-model="loginForm.username" :placeholder="$t('login.phAccount')" :prefix-icon="User" />
            </el-form-item>

            <div class="field-label">
              {{ $t('login.labelPassword') }}
              <span class="forgot">{{ $t('login.forgot') }}</span>
            </div>
            <el-form-item prop="password">
              <el-input
                v-model="loginForm.password"
                type="password"
                :placeholder="$t('login.phPassword')"
                show-password
                :prefix-icon="Lock"
                @keyup.enter="handleLogin"
              />
            </el-form-item>

            <div class="login-options">
              <el-checkbox v-model="rememberMe">{{ $t('login.remember') }}</el-checkbox>
              <span class="sso-text"><el-icon><Check /></el-icon> {{ $t('login.sso') }}</span>
            </div>

            <el-button type="primary" class="login-btn" :loading="loading" @click="handleLogin">
              {{ $t('login.loginBtn') }} <el-icon><Right /></el-icon>
            </el-button>

            <div class="login-tip">
              <el-icon><InfoFilled /></el-icon>
              <span><b>{{ $t('login.permTipLabel') }}</b>{{ $t('login.permTipBody') }}</span>
            </div>
          </el-form>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, Check, Right, InfoFilled } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const { t } = useI18n()

const loginFormRef = ref<FormInstance>()
const loading = ref(false)
const rememberMe = ref(true)

const loginForm = reactive({
  username: 'employee',
  password: '123456'
})

const loginRules = computed<FormRules>(() => ({
  username: [{ required: true, message: t('login.ruleUsername'), trigger: 'blur' }],
  password: [{ required: true, message: t('login.rulePassword'), trigger: 'blur' }]
}))

const handleLogin = async () => {
  if (!loginFormRef.value) return
  const valid = await loginFormRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await userStore.login(loginForm.username, loginForm.password)
    ElMessage.success(t('login.loginSuccess'))
    // 按角色跳转：审批人进审批工作台，普通员工进员工工作台
    router.push(userStore.userInfo?.role === 'admin' ? '/dashboard/admin' : '/dashboard/employee')
  } catch (e: any) {
    ElMessage.error(e || t('login.loginFailed'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(ellipse 60% 40% at 15% 0%, rgba(245, 73, 31, 0.07), transparent),
    var(--af-bg);
}

.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--af-primary); }
.dot.green { background: var(--af-success); }

/* ===== 顶部品牌栏 ===== */
.login-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 40px;
  border-bottom: 1px solid var(--af-border-soft);
}

.brand { display: flex; align-items: center; gap: 12px; }
.brand-logo {
  width: 40px; height: 40px;
  background: var(--af-primary-gradient);
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  color: #fff;
}
.brand-text { display: flex; flex-direction: column; }
.brand-name { color: var(--af-text); font-weight: 700; font-size: 18px; }
.brand-by { color: var(--af-text-3); font-size: 11px; }
.brand-tag {
  margin-left: 8px;
  font-size: 10px;
  color: var(--af-text-3);
  background: var(--af-card);
  border: 1px solid var(--af-border);
  border-radius: 8px;
  padding: 4px 10px;
  line-height: 1.4;
}

.header-right { display: flex; align-items: center; gap: 12px; }
.header-pill {
  display: inline-flex; align-items: center; gap: 7px;
  color: var(--af-text-2);
  font-size: 12px;
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 20px;
  padding: 6px 14px;
  max-width: 200px;
}

/* ===== 主体两栏 ===== */
.login-body {
  /* 不再占满剩余高度，高度由内容决定，上下 margin:auto 使其在页面垂直居中 */
  margin: auto 0;
  display: flex;
  gap: 60px;
  padding: 32px 64px;
  /* 两栏底部对齐，卡片高度各自由内容决定 */
  align-items: flex-end;
  justify-content: center;
}

/* 左侧介绍区 */
.hero-side {
  max-width: 560px;
  flex: 1.2;
  padding-top: 8px;
  display: flex;
  flex-direction: column;
}

.hero-badge {
  display: inline-flex; align-items: center; gap: 8px;
  color: var(--af-text-2);
  font-size: 12px;
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 20px;
  padding: 7px 16px;
  margin-bottom: 28px;
}

.hero-title {
  font-size: 46px;
  line-height: 1.25;
  font-weight: 800;
  color: var(--af-text);
  margin-bottom: 20px;
}
.gradient-text {
  background: linear-gradient(100deg, #ffb03a 0%, #ff6a3d 55%, #f5491f 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.hero-desc { color: var(--af-text-2); font-size: 15px; line-height: 1.9; margin-bottom: 32px; max-width: 520px; }

.hero-card {
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius);
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  /* 高度跟随内容，不强制撑满 */
  flex: none;
}

.hero-card-head {
  display: flex; justify-content: space-between; align-items: center;
  color: var(--af-text); font-size: 13px; font-weight: 600;
}
.hero-card-head .dot { margin-right: 6px; }
.coord-tag {
  font-size: 11px; color: var(--af-warning);
  background: var(--af-warning-soft);
  border-radius: 6px; padding: 3px 10px;
}

.hero-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.hero-stat {
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  padding: 12px 14px;
}
.hs-label { color: var(--af-text-2); font-size: 12px; margin-bottom: 8px; }
.hs-value { color: var(--af-text); font-size: 22px; font-weight: 800; }
.hs-value span { font-size: 10px; font-weight: 400; color: var(--af-text-3); margin-left: 4px; }
.hs-value.orange { color: #ff6a3d; }
.hs-value.green { color: var(--af-success); }

.hero-pipeline { display: flex; flex-direction: column; gap: 10px; }
.pipe-item {
  display: flex; align-items: center; gap: 12px;
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  padding: 12px 14px;
}
.pipe-num {
  width: 26px; height: 26px; flex-shrink: 0;
  border-radius: 8px;
  background: var(--af-primary-soft);
  color: var(--af-primary);
  font-size: 12px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.pipe-text { flex: 1; min-width: 0; }
.pipe-text b { display: block; color: var(--af-text); font-size: 13px; font-weight: 600; }
.pipe-text i { display: block; color: var(--af-text-3); font-size: 11px; font-style: normal; margin-top: 3px; }
.pipe-state { flex-shrink: 0; font-size: 11px; }
.pipe-state.green { color: var(--af-success); display: inline-flex; align-items: center; gap: 4px; }
.pipe-state.orange { color: var(--af-warning); }

.hero-foot {
  display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  color: var(--af-text-3); font-size: 11px;
}
.hero-foot span { display: inline-flex; align-items: center; gap: 5px; }

/* 右侧登录卡片 */
.form-side { flex: 1; display: flex; justify-content: center; max-width: 480px; width: 100%; padding-top: 8px; }

.login-card {
  width: 100%;
  max-width: 420px;
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 16px;
  padding: 32px 30px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.45);
}

.login-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 26px; }
.login-head h2 { color: var(--af-text); font-size: 24px; font-weight: 700; margin-bottom: 8px; }
.login-head p { color: var(--af-text-3); font-size: 12px; }
.card-tag {
  flex-shrink: 0;
  color: var(--af-text-2);
  font-size: 11px;
  background: var(--af-card-soft);
  border: 1px solid var(--af-border);
  border-radius: 6px;
  padding: 4px 10px;
  text-align: center;
  line-height: 1.4;
}

.field-label {
  display: flex; justify-content: space-between; align-items: center;
  color: var(--af-text-2); font-size: 12px; margin-bottom: 8px;
}
.forgot { color: var(--af-primary); cursor: pointer; }

.login-options {
  display: flex; justify-content: space-between; align-items: center;
  margin: 4px 0 20px;
}
.login-options :deep(.el-checkbox__label) { color: var(--af-text-2); font-size: 12px; }
.sso-text { display: inline-flex; align-items: center; gap: 4px; color: var(--af-text-3); font-size: 11px; }

.login-btn {
  width: 100%;
  height: 46px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 6px;
  border: none;
  background: var(--af-primary-gradient);
  border-radius: 10px;
}
.login-btn:hover { opacity: 0.9; }

.login-tip {
  display: flex; gap: 8px;
  margin-top: 20px;
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  padding: 12px 14px;
  color: var(--af-text-3);
  font-size: 11px;
  line-height: 1.7;
}
.login-tip .el-icon { margin-top: 3px; color: var(--af-warning); flex-shrink: 0; }
.login-tip b { color: var(--af-text-2); font-weight: 600; }

/* ===== 移动端适配（参照 mobile_1：上下堆叠） ===== */
@media (max-width: 900px) {
  .login-body { flex-direction: column; padding: 24px 18px; gap: 28px; align-items: center; }
  .hero-side { max-width: 480px; width: 100%; padding-top: 0; }
  .hero-title { font-size: 30px; }
  .hero-desc { font-size: 13px; margin-bottom: 22px; }
  .hero-stats { grid-template-columns: repeat(3, 1fr); }
  .pipe-item { align-items: flex-start; }
  .form-side { max-width: 480px; padding-top: 0; }
}

@media (max-width: 480px) {
  .login-header { padding: 14px 16px; }
  .header-pill { display: none; }
  .login-body { padding: 18px 14px; }
  .hero-title { font-size: 25px; }
  .login-card { padding: 24px 20px; }
  .login-btn { letter-spacing: 3px; }
}
</style>
