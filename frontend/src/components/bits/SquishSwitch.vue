<script setup lang="ts">
/** 挤压回弹开关（vue-bits SquishSwitch 的手写等价实现）。
 *  L1 必要反馈：按下拇指挤压（scaleX 0.7），松开弹性回弹（back easing）。
 *  jsrepo 拉取 vue-bits registry 失败（端点返回 HTML），按设计文档 §8
 *  "源码入库、自有代码二次维护"原则手写，不引入 motion-v。 */
defineProps<{ value: boolean; disabled?: boolean; size?: 'small' | 'medium' }>()
const emit = defineEmits<{ (e: 'update:value', v: boolean): void }>()
</script>

<template>
  <button
    class="sq-switch"
    :class="[size ?? 'medium', { checked: value, disabled }]"
    role="switch"
    :aria-checked="value"
    type="button"
    @click="!disabled && emit('update:value', !value)"
  >
    <span class="thumb" />
  </button>
</template>

<style scoped>
.sq-switch {
  position: relative;
  flex: none;
  border: 1px solid var(--ops-border);
  border-radius: 999px;
  background: var(--ops-surface-2);
  cursor: pointer;
  padding: 0;
  transition: background 180ms ease, border-color 180ms ease;
  /* medium 默认尺寸（对齐 NSwitch medium 34x20） */
  width: 34px;
  height: 20px;
}
.sq-switch.small {
  width: 28px;
  height: 16px;
}
.sq-switch.checked {
  background: var(--ops-primary);
  border-color: var(--ops-primary);
}
.sq-switch.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.thumb {
  position: absolute;
  left: 2px;
  top: 50%;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  transform: translateY(-50%);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
  /* 回弹曲线：over-shoot 产生弹性感 */
  transition:
    left 220ms cubic-bezier(0.34, 1.56, 0.64, 1),
    transform 140ms ease;
}
.small .thumb {
  width: 11px;
  height: 11px;
}
.checked .thumb {
  left: calc(100% - 16px);
}
.small.checked .thumb {
  left: calc(100% - 13px);
}
/* 按住挤压，松手回弹 */
.sq-switch:not(.disabled):active .thumb {
  transform: translateY(-50%) scaleX(0.68);
}
@media (prefers-reduced-motion: reduce) {
  .thumb { transition: none; }
  .sq-switch:not(.disabled):active .thumb { transform: translateY(-50%); }
}
</style>
