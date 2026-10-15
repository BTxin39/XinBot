<template>
  <div class="chat-area" ref="scrollRef">
    <div class="messages">
      <MessageBubble
        v-for="(m, i) in messages"
        :key="i"
        :role="m.role"
        :content="m.content"
        :done="m.done"
      />
      <div v-if="!messages.length" class="welcome">
        <p>👋 你好！我是你的 AI 桌宠~</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, nextTick } from "vue";
import MessageBubble from "./MessageBubble.vue";

const messages = reactive([]);
const scrollRef = ref(null);
const streaming = ref(null);

function addMessage(role, content) {
  messages.push({ role, content, done: true });
  scrollDown();
}

function setStreaming(msg) {
  messages.push(msg);
  streaming.value = msg;
}

watch(
  () => streaming.value?.content,
  () => scrollDown()
);

function scrollDown() {
  nextTick(() => {
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight;
    }
  });
}

defineExpose({ messages, addMessage, setStreaming });
</script>

<style scoped>
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
}
.messages {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.welcome {
  text-align: center;
  color: var(--text-muted);
  margin-top: 40vh;
  font-size: 16px;
}
</style>
