<!-- File: frontend/src/components/BulkReviewConfirmation.vue -->
<template>
  <div v-if="snapshot" class="space-y-2 text-slate-300">
    <p>OWNER: {{ snapshot.owner_name }} · Người gửi: {{ snapshot.sender_name }} · Chữ ký: {{ snapshot.owner_name }} · Thẩm quyền: {{ snapshot.rights_jurisdiction }}</p>
    <label class="flex gap-2">
      <input type="checkbox" :checked="accepted" :disabled="disabled" @change="$emit('update:accepted', $event.target.checked)" />
      Tôi đã xem hồ sơ hiện tại, thứ tự đơn và mail được gán; xác nhận dùng hồ sơ này khi Chạy.
    </label>
  </div>
</template>
<script setup>
defineProps({snapshot:{type:Object, default:null}, accepted:{type:Boolean, default:false}, disabled:{type:Boolean, default:true}});
defineEmits(['update:accepted']);
</script>
