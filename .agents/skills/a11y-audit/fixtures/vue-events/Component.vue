<template>
  <!-- H2 positive — Vue @click shorthand on a non-interactive element. -->
  <div @click="handleClick" class="cta">Get started</div>

  <!-- H2 positive — Vue modifier syntax. -->
  <div @click.stop="onAction">stop modifier</div>

  <!-- H2 positive — chained modifiers. -->
  <span @click.prevent.stop="onAction">prevent + stop</span>

  <!-- H2 positive — long-form v-on:click on a non-interactive element. -->
  <div v-on:click="onAction">long form</div>

  <!-- H2 negative — @click on a real button is not a violation. -->
  <button type="button" @click="okay">View pricing</button>
</template>
