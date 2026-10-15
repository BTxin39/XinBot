<template>
  <nav class="navbar">
    <div class="brand">XinBot</div>
    <div class="links">
      <router-link to="/">对话</router-link>
      <router-link to="/persona">角色</router-link>
      <router-link to="/knowledge">知识库</router-link>
      <router-link to="/settings">设置</router-link>
    </div>
  </nav>
</template>

<style scoped>
.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 48px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.brand {
  font-weight: 700;
  font-size: 16px;
  color: var(--accent);
}

.links {
  display: flex;
  gap: 4px;
}

.links a {
  color: var(--text-muted);
  text-decoration: none;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s;
}

.links a:hover,
.links a.router-link-active {
  color: var(--text);
  background: var(--bg-card);
}
</style>
