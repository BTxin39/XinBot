<template>
  <div class="pet-mini" @click="$emit('click')">
    <span class="mini-emoji">🐱</span>
  </div>
</template>

<script setup>
import { ref } from "vue";
import api from "../api.js";

const emoji = ref("🐱");
const emotionEmojis = {
  normal: "🐱", happy: "😸", sad: "😿", angry: "😾", sleepy: "😴",
};

async function updateEmoji() {
  const r = await api.getStatus();
  if (r.ok) {
    emoji.value = emotionEmojis[r.data.emotion] || "🐱";
  }
}

updateEmoji();
setInterval(updateEmoji, 5000);
</script>

<style scoped>
.pet-mini {
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.2s;
}

.pet-mini:hover {
  transform: scale(1.1);
}

.mini-emoji {
  font-size: 48px;
}
</style>
