---
layout: page
title: Our Jam Circles
permalink: /jam-circles/
---

We currently run jam circles weekly in Galway & Clare with more circles opening up in each county.

<div class="circles-grid" markdown="0">
  {% for circle in site.data.circles %}
  <a href="{{ circle.url | relative_url }}" class="circle-card">
    <img src="{{ circle.image | relative_url }}" alt="{{ circle.name }} Jam Circle">
    <div class="circle-card-body">
      <h3>{{ circle.name }}</h3>
      <p>{{ circle.summary }}</p>
    </div>
  </a>
  {% endfor %}
</div>
