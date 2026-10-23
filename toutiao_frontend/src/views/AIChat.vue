<template>
  <div class="ai-chat-container">
    <van-nav-bar title="AI问答" fixed>
      <template #right>
        <span class="history-link" @click="openHistory">历史</span>
      </template>
    </van-nav-bar>

    <div class="chat-content">
      <div class="messages-container" ref="messagesContainer">
        <div
          v-for="(message, index) in messages"
          :key="index"
          :class="['message', message.role === 'user' ? 'user-message' : 'ai-message']"
        >
          <div class="message-content">
            <div
              v-if="message.role === 'assistant' && message.content === ''"
              class="typing-indicator"
            >
              <span></span>
              <span></span>
              <span></span>
              <span v-if="isLoading && statusText" class="typing-text">{{ statusText }}</span>
            </div>
            <div v-else v-html="formatMessage(message.content)"></div>

            <div
              v-if="message.role === 'assistant' && message.sources && message.sources.length"
              class="sources"
            >
              <div class="sources-title">参考新闻</div>
              <div
                v-for="source in message.sources"
                :key="`${source.newsId}-${source.index}`"
                class="source-card"
                @click="goDetail(source.newsId)"
              >
                <span class="source-index">[{{ source.index }}]</span>
                <div class="source-info">
                  <div class="source-title-text">{{ source.title }}</div>
                  <div class="source-meta">
                    {{ source.category || '未分类' }} · {{ source.publishTime || '时间未知' }} ·
                    {{ source.author || '未知作者' }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="input-container">
        <van-field
          v-model="userInput"
          rows="1"
          autosize
          type="textarea"
          placeholder="请输入问题..."
          class="chat-input"
          @keypress.enter.prevent="sendMessage"
        />
        <van-button
          type="primary"
          class="send-button"
          :disabled="isLoading || !userInput.trim()"
          :loading="isLoading"
          @click="sendMessage"
        >
          发送
        </van-button>
      </div>
    </div>

    <van-popup
      v-model:show="showHistory"
      position="bottom"
      round
      :style="{ height: '70%' }"
    >
      <div class="history-panel">
        <div class="history-header">
          <span>
            历史提问
            <span v-if="historyTotal" class="history-count">（{{ historyTotal }}）</span>
          </span>
          <van-button
            size="small"
            type="danger"
            plain
            :disabled="!historyList.length"
            @click="clearHistory"
          >
            清空
          </van-button>
        </div>

        <div class="history-body">
          <van-empty
            v-if="!historyLoading && !historyList.length"
            description="暂无历史提问"
          />
          <div v-for="item in historyList" :key="item.id" class="history-item">
            <div class="history-question">{{ item.message }}</div>
            <div class="history-answer">{{ item.response }}</div>
            <div class="history-time">{{ formatTime(item.createdAt) }}</div>
          </div>
          <div v-if="historyHasMore" class="history-more">
            <van-button size="small" :loading="historyLoading" @click="loadHistory(false)">
              加载更多
            </van-button>
          </div>
          <div v-else-if="historyList.length" class="history-end">没有更多了</div>
        </div>
      </div>
    </van-popup>

    <tab-bar />
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue';
import { useRouter } from 'vue-router';
import TabBar from '../components/TabBar.vue';
import { showToast, showConfirmDialog } from 'vant';
import * as marked from 'marked';
import DOMPurify from 'dompurify';
import { aiChatConfig } from '../config/api';
import { useUserStore } from '../store/user';

const router = useRouter();
const userStore = useUserStore();

// 聊天消息
const messages = ref([
  {
    role: 'assistant',
    content: '你好！我是新闻 AI 助手。你可以问我新闻库里的最新报道、分类新闻，或某条新闻的细节。',
    sources: []
  }
]);
const userInput = ref('');
const messagesContainer = ref(null);
const isLoading = ref(false);
const statusText = ref('');

// 历史弹窗
const showHistory = ref(false);
const historyList = ref([]);
const historyLoading = ref(false);
const historyTotal = ref(0);
const historyPage = ref(1);
const historyHasMore = ref(false);

// 格式化消息内容（支持Markdown）
const formatMessage = (content) => {
  if (!content) return '';
  // 兼容模型偶尔漏掉标题前空行的情况，避免 ## 被当成普通文本
  const normalized = content.replace(/([^\n])(#{1,6}\s)/g, '$1\n\n$2');
  return DOMPurify.sanitize(marked.parse(normalized));
};

const formatTime = (value) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (number) => String(number).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
  }
};

const scrollSoon = () => {
  nextTick(scrollToBottom);
};

const goLogin = () => {
  router.push({ path: '/login', query: { redirect: '/aichat' } });
};

const goDetail = (newsId) => {
  if (newsId) {
    router.push(`/news/detail/${newsId}`);
  }
};

// 发送消息
const sendMessage = async () => {
  const text = userInput.value.trim();
  if (!text || isLoading.value) return;

  if (!userStore.token) {
    showToast('请先登录');
    goLogin();
    return;
  }

  messages.value.push({ role: 'user', content: text });
  messages.value.push({ role: 'assistant', content: '', sources: [], chatId: null });
  userInput.value = '';
  isLoading.value = true;
  statusText.value = '正在检索新闻库...';

  await nextTick();
  scrollToBottom();

  try {
    await fetchAIResponse(text);
  } catch (error) {
    console.error('AI chat error:', error);
    const last = messages.value[messages.value.length - 1];

    if (error.status === 401) {
      messages.value.splice(-2);
      userStore.logout();
      showToast('登录已过期，请重新登录');
      goLogin();
      return;
    }

    if (last.content) {
      last.content += `\n\n> ${error.message || 'AI 服务暂时不可用，请稍后再试。'}`;
    } else {
      last.content = `抱歉，${error.message || 'AI 服务暂时不可用，请稍后再试。'}`;
    }
    last.sources = [];
  } finally {
    isLoading.value = false;
    statusText.value = '';
    await nextTick();
    scrollToBottom();
  }
};

// 获取AI响应（SSE）
const fetchAIResponse = async (userMessage) => {
  const response = await fetch(aiChatConfig.chatEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': userStore.token
    },
    body: JSON.stringify({ message: userMessage })
  });

  if (response.status === 401) {
    const error = new Error('登录已过期');
    error.status = 401;
    throw error;
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || error.message || `请求失败（${response.status}）`);
  }

  if (!response.body) {
    throw new Error('当前浏览器不支持流式响应');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let received = false;
  const current = messages.value[messages.value.length - 1];

  const handleEvent = (rawEvent) => {
    const lines = rawEvent.split('\n');
    let event = 'message';
    const dataLines = [];

    for (const line of lines) {
      const clean = line.replace(/\r$/, '');
      if (clean.startsWith('event:')) {
        event = clean.slice(6).trim();
      } else if (clean.startsWith('data:')) {
        dataLines.push(clean.slice(5).trim());
      }
    }

    if (!dataLines.length) return;

    let payload;
    try {
      payload = JSON.parse(dataLines.join('\n'));
    } catch (error) {
      console.warn('SSE JSON parse error:', error);
      return;
    }

    if (event === 'status') {
      statusText.value = payload.message || '';
    } else if (event === 'reset') {
      current.content = '';
      current.sources = [];
      received = false;
    } else if (event === 'delta') {
      if (payload.content) {
        current.content += payload.content;
        received = true;
        scrollSoon();
      }
    } else if (event === 'sources') {
      current.sources = Array.isArray(payload.sources) ? payload.sources : [];
      scrollSoon();
    } else if (event === 'done') {
      current.chatId = payload.chatId ?? null;
      if (showHistory.value) {
        loadHistory(true);
      }
    } else if (event === 'error') {
      current.content = payload.message || 'AI 服务暂时不可用，请稍后再试。';
      received = true;
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';

    for (const part of parts) {
      if (part.trim()) handleEvent(part);
    }
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    handleEvent(buffer.replace(/\r\n/g, '\n'));
  }

  if (!received) {
    current.content = '抱歉，我暂时无法回答这个问题，请换一种问法或稍后重试。';
  }
};

// 历史记录
const loadHistory = async (reset = false) => {
  if (historyLoading.value) return;

  if (reset) {
    historyPage.value = 1;
    historyList.value = [];
    historyHasMore.value = true;
  }

  if (!reset && !historyHasMore.value) return;

  historyLoading.value = true;
  try {
    const response = await fetch(
      `${aiChatConfig.historyEndpoint}?page=${historyPage.value}&pageSize=10`,
      {
        headers: { Authorization: userStore.token }
      }
    );

    if (response.status === 401) {
      userStore.logout();
      showToast('登录已过期，请重新登录');
      goLogin();
      return;
    }

    const body = await response.json();
    if (!response.ok || body.code !== 200) {
      throw new Error(body.detail || body.message || '加载历史失败');
    }

    const data = body.data || {};
    const list = Array.isArray(data.list) ? data.list : [];
    historyList.value = reset ? list : [...historyList.value, ...list];
    historyTotal.value = data.total || 0;
    historyHasMore.value = Boolean(data.hasMore);
    if (data.hasMore) {
      historyPage.value += 1;
    }
  } catch (error) {
    console.error('Load history error:', error);
    showToast(error.message || '加载历史失败');
  } finally {
    historyLoading.value = false;
  }
};

const openHistory = () => {
  showHistory.value = true;
  loadHistory(true);
};

const clearHistory = async () => {
  try {
    await showConfirmDialog({
      title: '清空历史',
      message: '确定清空全部 AI 提问历史吗？清空后不可恢复。'
    });
  } catch {
    return;
  }

  try {
    const response = await fetch(aiChatConfig.historyEndpoint, {
      method: 'DELETE',
      headers: { Authorization: userStore.token }
    });

    if (response.status === 401) {
      userStore.logout();
      showToast('登录已过期，请重新登录');
      goLogin();
      return;
    }

    const body = await response.json();
    if (!response.ok || body.code !== 200) {
      throw new Error(body.detail || body.message || '清空失败');
    }

    historyList.value = [];
    historyTotal.value = 0;
    historyHasMore.value = false;
    showToast('已清空历史');
  } catch (error) {
    console.error('Clear history error:', error);
    showToast(error.message || '清空失败');
  }
};

// 监听消息变化，自动滚动
watch(messages, () => {
  scrollSoon();
}, { deep: true });

onMounted(() => {
  scrollToBottom();
});
</script>

<style scoped>
.ai-chat-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding-top: 46px;
  padding-bottom: 50px;
  box-sizing: border-box;
}

.history-link {
  color: #1989fa;
  font-size: 14px;
}

.chat-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.message {
  margin-bottom: 10px;
  max-width: 80%;
}

.user-message {
  margin-left: auto;
}

.ai-message {
  margin-right: auto;
}

.message-content {
  padding: 10px;
  border-radius: 10px;
  word-break: break-word;
}

.user-message .message-content {
  background-color: #007aff;
  color: white;
}

.ai-message .message-content {
  background-color: #f2f2f2;
  color: #333;
}

.input-container {
  display: flex;
  padding: 10px;
  border-top: 1px solid #eee;
  background-color: #fff;
}

.chat-input {
  flex: 1;
  margin-right: 10px;
}

.send-button {
  align-self: flex-end;
}

/* 来源卡片 */
.sources {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #d9d9d9;
}

.sources-title {
  margin-bottom: 6px;
  color: #888;
  font-size: 12px;
}

.source-card {
  display: flex;
  gap: 6px;
  margin-bottom: 6px;
  padding: 7px;
  background: #fff;
  border: 1px solid #eee;
  border-radius: 6px;
  cursor: pointer;
}

.source-card:active {
  background: #f7f8fa;
}

.source-index {
  flex-shrink: 0;
  color: #1989fa;
  font-size: 12px;
}

.source-title-text {
  color: #333;
  font-size: 13px;
  line-height: 1.4;
}

.source-meta {
  margin-top: 2px;
  color: #999;
  font-size: 11px;
  line-height: 1.4;
}

/* 历史弹窗 */
.history-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  box-sizing: border-box;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
}

.history-count {
  color: #999;
  font-size: 12px;
  font-weight: 400;
}

.history-body {
  flex: 1;
  overflow-y: auto;
}

.history-item {
  padding: 10px 0;
  border-bottom: 1px solid #f0f0f0;
}

.history-question {
  margin-bottom: 4px;
  color: #333;
  font-size: 14px;
  font-weight: 500;
  word-break: break-word;
}

.history-answer {
  display: -webkit-box;
  overflow: hidden;
  color: #666;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.history-time {
  margin-top: 4px;
  color: #aaa;
  font-size: 11px;
}

.history-more,
.history-end {
  padding: 12px 0;
  color: #999;
  font-size: 12px;
  text-align: center;
}

/* Markdown 样式 */
.message-content pre {
  background-color: #f8f8f8;
  padding: 10px;
  border-radius: 5px;
  overflow-x: auto;
}

.message-content code {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 2px 4px;
  border-radius: 3px;
}

.message-content img {
  max-width: 100%;
}

/* 打字指示器 */
.typing-indicator {
  display: flex;
  align-items: center;
  padding: 5px;
}

.typing-indicator span {
  height: 8px;
  width: 8px;
  background-color: #999;
  border-radius: 50%;
  margin: 0 2px;
  display: inline-block;
  animation: bounce 1.5s infinite ease-in-out;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

.typing-text {
  width: auto;
  height: auto;
  margin-left: 6px;
  background: transparent;
  color: #999;
  font-size: 12px;
  animation: none;
}

@keyframes bounce {
  0%, 60%, 100% {
    transform: translateY(0);
  }
  30% {
    transform: translateY(-5px);
  }
}

/* Markdown样式 */
:deep(pre) {
  background-color: #f0f0f0;
  padding: 10px;
  border-radius: 4px;
  overflow-x: auto;
}

:deep(code) {
  font-family: monospace;
  background-color: #f0f0f0;
  padding: 2px 4px;
  border-radius: 4px;
}

:deep(p) {
  margin: 8px 0;
}

:deep(ul), :deep(ol) {
  padding-left: 20px;
}

:deep(a) {
  color: #1989fa;
  text-decoration: none;
}
</style>
