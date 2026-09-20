<template>
  <div class="chat-input">
    <input
      ref="inputRef"
      v-model="text"
      placeholder="输入消息..."
      @keyup.enter="send"
      :disabled="disabled"
    />
    <button @click="send" :disabled="disabled || !text.trim()">发送</button>
  </div>
</template>

<script setup>
import { ref } from "vue";

const props = defineProps({ disabled: Boolean });
const emit = defineEmits(["send"]);
const text = ref("");
const inputRef = ref(null);

function send() {
  const msg = text.value.trim();
  if (!msg || props.disabled) return;
  emit("send", msg);
  text.value = "";
  inputRef.value?.focus();
}
</script>

<style scoped>
.chat-input {
  display: flex;
  gap: 8px;
  padding: 12px 24px;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
}

.chat-input input {
  flex: 1;
}
</style>
