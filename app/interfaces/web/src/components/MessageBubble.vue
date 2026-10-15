<script setup>
import { computed } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { Copy } from 'lucide-vue-next';
import { character, report } from '../state.js';
const props = defineProps({ message: Object });
const html = computed(() => DOMPurify.sanitize(marked.parse(props.message.content || '')));
async function copy() { try { await navigator.clipboard.writeText(props.message.content); } catch(error) { report(error); } }
</script>
<template><article class="message" :class="message.role"><div class="message-meta"><span>{{ message.role === 'user' ? '你' : character?.display_name || 'Xin' }}</span><button class="icon-button" title="复制消息" @click="copy"><Copy :size="14"/></button></div><div class="prose" v-html="html"/></article></template>
