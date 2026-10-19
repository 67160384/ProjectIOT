"use strict";
const canvas = document.querySelector('#expense-chart');
if (canvas) {
  fetch(`/api/summary?month=${encodeURIComponent(canvas.dataset.month)}`).then(r=>{if(!r.ok)throw new Error();return r.json();}).then(data=>{
    new Chart(canvas, {
      type: 'bar',
      data: {
        labels: data.categories.map(c => c.category),
        datasets: [{
          data: data.categories.map(c => c.amount / 100),
          backgroundColor: ['#176451','#86a967','#b5ca84','#d2df9f','#668879','#c8a664','#b98573'],
          borderRadius: 5, maxBarThickness: 28
        }]
      },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: {display: false},
          tooltip: {callbacks: {label: context => new Intl.NumberFormat('th-TH', {style:'currency',currency:'THB'}).format(context.parsed.x)}}
        },
        scales: {
          x: {grid:{color:'#eef1e9'}, ticks:{font:{family:'Thai'},color:'#80907c'}},
          y: {grid:{display:false}, ticks:{font:{family:'Thai',size:11},color:'#536b59'}}
        }
      }
    });
  }).catch(()=>{canvas.parentElement.textContent = 'โหลดกราฟไม่สำเร็จ ดูยอดจากตารางด้านล่างได้';});
}
