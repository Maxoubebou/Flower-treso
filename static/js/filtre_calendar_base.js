(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        // --- 1. Gestion des filtres de mois ---
        const monthToggle = document.getElementById('month-toggle');
        const monthMenu = document.getElementById('month-menu');
        const filterForm = document.getElementById('month-filter-form');
        const btnVider = document.getElementById('btn-vider-mois');
        const btnTous = document.getElementById('btn-tous-mois');

        if (monthToggle && monthMenu) {
            monthToggle.addEventListener('click', (e) => {
                e.stopPropagation();
                monthMenu.classList.toggle('show');
            });

            // Fermer le menu si on clique ailleurs
            document.addEventListener('click', (e) => {
                if (!monthMenu.contains(e.target)) {
                    monthMenu.classList.remove('show');
                }
            });
        }

        if (btnVider && filterForm) {
            btnVider.addEventListener('click', (e) => {
                e.preventDefault();
                filterForm.querySelectorAll('input[name="mois"]').forEach(cb => cb.checked = false);
                
                // Forcer le backend à voir une valeur vide
                const hidden = document.createElement('input');
                hidden.type = 'hidden';
                hidden.name = 'mois';
                hidden.value = ''; 
                filterForm.appendChild(hidden);
                filterForm.submit();
            });
        }

        if (btnTous && filterForm) {
            btnTous.addEventListener('click', (e) => {
                e.preventDefault();
                filterForm.querySelectorAll('input[name="mois"]').forEach(cb => cb.checked = true);
                filterForm.submit();
            });
        }

        // --- 2. Interface (Icons & Sidebar) ---
        if (window.lucide) {
            lucide.createIcons();
        }

        const sidebar = document.getElementById('sidebar');
        const mainContent = document.querySelector('.main-content');
        const toggleBtn = document.getElementById('toggle-sidebar');

        if (sidebar && mainContent) {
            // État initial
            if (localStorage.getItem('sidebarCollapsed') === 'true') {
                sidebar.classList.add('collapsed');
                mainContent.classList.add('collapsed');
            }

            if (toggleBtn) {
                toggleBtn.addEventListener('click', function() {
                    sidebar.classList.toggle('collapsed');
                    mainContent.classList.toggle('collapsed');
                    localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
                });
            }
        }
    });
})();