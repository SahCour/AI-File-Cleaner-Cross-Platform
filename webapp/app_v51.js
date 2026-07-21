let globalFiles = [];
let globalFlatDests = [];
let currentFilter = 'ALL';
let viewMode = 'SOURCE'; // 'SOURCE' or 'DEST'
let searchQuery = '';
let groupLimits = {};
let dynamicActions = [];
let destinations = {};

document.addEventListener('DOMContentLoaded', async () => {
    try {
        let destRes = await fetch('/api/get_destinations').catch(() => null);
        if (!destRes || !destRes.ok) {
            destRes = await fetch('../destinations.json?v=4');
        }
        destinations = await destRes.json();
        
        for (const [category, paths] of Object.entries(destinations)) {
            paths.forEach(p => {
                let emoji = '📁';
                if (category.toLowerCase().includes('personal') || category.toLowerCase() === 'health') {
                    emoji = '🏠';
                } else if (category.toLowerCase().includes('biz') || category.toLowerCase() === 'projects' || category.toLowerCase() === 'finance') {
                    emoji = '💼';
                } else if (category.toLowerCase().includes('ai')) {
                    emoji = '🤖';
                }
                
                const parts = p.split('/').filter(x => x !== '');
                let label = parts[parts.length - 1];
                
                if (category === 'Custom' && parts.length >= 2) {
                    label = `${parts[parts.length - 2]} / ${label}`;
                }
                
                let color = '#4db6ac';globalFlatDests.push({category, path: p});
            });
        }
        
        buildDynamicActions();
        
        const fileRes = await fetch('../files_to_process.json');
        const rawFiles = await fileRes.json();
        
        // Add reactive properties
        globalFiles = rawFiles.map(f => {
            const dest = f.suggested_folder || '~/_Quarantine/To_Review';
            return {
                ...f,
                original_dest: dest,
                current_dest: dest,
                selected: false
            };
        });
        
        // Restore Progress
        try {
            const saved = localStorage.getItem('macCleanerProgress');
            if (saved) {
                const progress = JSON.parse(saved);
                globalFiles.forEach(f => {
                    if (progress[f.id]) {
                        f.current_dest = progress[f.id].current_dest;
                        f.selected = progress[f.id].selected;
                        f.is_dir_move = progress[f.id].is_dir_move;
                        f.parent_dir_to_move = progress[f.id].parent_dir_to_move;
                        f.reviewed = progress[f.id].reviewed || false;
                    }
                });
            }
        } catch (e) {
            console.error("Failed to restore progress", e);
        }
        
        let newlyFound = false;
        globalFiles.forEach(f => {
            if (f.current_dest && f.current_dest !== 'DELETE' && f.current_dest !== '~/_Quarantine/To_Review' && f.current_dest !== 'To_Review') {
                let found = false;
                for (const paths of Object.values(destinations)) {
                    if (paths.includes(f.current_dest)) {
                        found = true;
                        break;
                    }
                }
                if (!found) {
                    if (!destinations['Custom']) destinations['Custom'] = [];
                    if (!destinations['Custom'].includes(f.current_dest)) {
                        destinations['Custom'].push(f.current_dest);
                        globalFlatDests.push({category: 'Custom', path: f.current_dest});
                        newlyFound = true;
                    }
                }
            }
        });
        
        if (newlyFound) {
            buildDynamicActions();
            // Optionally try to save these newly discovered paths to the backend
            saveDestinationsToAPI().catch(() => {});
        }
        
        setupBulkBarOptions();
        renderUI();
        
    } catch (e) {
        console.error("Failed to load data", e);
        document.getElementById('file-list').innerHTML = `<div style="padding: 2rem; text-align: center; color: #ff5252;">Failed to load data.</div>`;
    }

    // Reset Progress Handler
    document.getElementById('btn-reset').addEventListener('click', () => {
        if (confirm("Are you sure you want to reset all manual progress and revert to AI suggestions?")) {
            localStorage.removeItem('macCleanerProgress');
            globalFiles.forEach(f => {
                f.current_dest = f.original_dest;
                f.selected = false;
                f.reviewed = false;
                f.is_dir_move = false;
            });
            renderUI();
        }
    });

    // View Mode Toggle Listeners
    document.getElementById('btn-mode-source').addEventListener('click', (e) => {
        viewMode = 'SOURCE';
        currentFilter = 'ALL';
        e.target.classList.add('active');
        e.target.style.borderColor = '#69f0ae';
        e.target.style.color = '#000';
        e.target.style.backgroundColor = '#69f0ae';
        e.target.style.fontWeight = 'bold';
        
        const destBtn = document.getElementById('btn-mode-dest');
        destBtn.classList.remove('active');
        destBtn.style.borderColor = 'var(--border)';
        destBtn.style.color = 'var(--text-main)';
        destBtn.style.backgroundColor = 'transparent';
        destBtn.style.fontWeight = 'normal';
        
        renderUI();
    });
    
    document.getElementById('btn-mode-dest').addEventListener('click', (e) => {
        viewMode = 'DEST';
        currentFilter = 'ALL';
        e.target.classList.add('active');
        e.target.style.borderColor = '#69f0ae';
        e.target.style.color = '#000';
        e.target.style.backgroundColor = '#69f0ae';
        e.target.style.fontWeight = 'bold';
        
        const srcBtn = document.getElementById('btn-mode-source');
        srcBtn.classList.remove('active');
        srcBtn.style.borderColor = 'var(--border)';
        srcBtn.style.color = 'var(--text-main)';
        srcBtn.style.backgroundColor = 'transparent';
        srcBtn.style.fontWeight = 'normal';
        
        renderUI();
    });

    // Search input listener
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            searchQuery = e.target.value.toLowerCase().trim();
            renderUI();
        });
    }

    // Export Handler
    document.getElementById('btn-export').addEventListener('click', () => {
        const exportData = globalFiles.filter(f => {
            return f.current_dest !== f.original_dest || f.reviewed || f.is_dir_move || f.current_dest === 'DELETE';
        }).map(f => {
            const payload = {
                id: f.id,
                filename: f.filename,
                path: f.path,
                destination: f.current_dest
            };
            if (f.is_dir_move) {
                payload.type = "DIR_MOVE";
                payload.path = f.parent_dir_to_move;
            }
            return payload;
        });
        
        const uniqueExportData = [];
        const seenDirs = new Set();
        exportData.forEach(item => {
            if (item.type === "DIR_MOVE") {
                if (!seenDirs.has(item.path)) {
                    seenDirs.add(item.path);
                    uniqueExportData.push(item);
                }
            } else {
                uniqueExportData.push(item);
            }
        });
        
        if (uniqueExportData.length === 0) {
            alert("No files have been organized yet!");
            return;
        }
        
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(uniqueExportData, null, 2));
        const anchor = document.createElement('a');
        anchor.setAttribute("href", dataStr);
        anchor.setAttribute("download", "export_tasks.json");
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
    });
    
    // Cancel Bulk Handler
    document.getElementById('btn-cancel-bulk').addEventListener('click', () => {
        globalFiles.forEach(f => f.selected = false);
        document.querySelectorAll('.file-checkbox, .group-checkbox').forEach(cb => cb.checked = false);
        const bulkRadios = document.querySelectorAll('#bulk-tags .quick-radio');
        bulkRadios.forEach(r => r.checked = false);
        updateBulkBarVisibility(); // Instant hide
        saveProgress();
    });
    
    // Bulk Apply Handler
    document.getElementById('btn-apply-bulk').addEventListener('click', () => {
        let selectedDest = null;
        
        const bulkRadios = document.querySelectorAll('#bulk-tags .quick-radio');
        bulkRadios.forEach(r => {
            if (r.checked) selectedDest = r.value;
        });
        
        if (!selectedDest) {
            alert("Please select a folder for mass action.");
            return;
        }
        
        // Apply to all selected files
        globalFiles.forEach(f => {
            if (f.selected) {
                f.current_dest = selectedDest;
                f.selected = false;
                f.reviewed = true;
            }
        });
        
        bulkRadios.forEach(r => r.checked = false);
        
        renderUI(); // Re-render to reflect soft-assignments
        saveProgress();
    });
});

function buildDynamicActions() {
    dynamicActions = [];
    
    const basePaths = {};
    globalFlatDests.forEach(d => {
        if (d.category !== 'Custom' && d.path !== 'DELETE' && !d.path.includes('To_Review')) {
            let c = '#ccc';
            let emoji = '📁';
            if (d.category.toLowerCase().includes('personal') || d.category.toLowerCase() === 'health') {
                c = '#69f0ae'; emoji = '🏠';
            } else if (d.category.toLowerCase().includes('biz') || d.category.toLowerCase() === 'projects' || d.category.toLowerCase() === 'finance') {
                c = '#448aff'; emoji = '💼';
            } else if (d.category.toLowerCase().includes('ai')) {
                c = '#e040fb'; emoji = '🤖';
            } else if (d.category === 'System') {
                c = '#b388ff'; emoji = '📦';
            }
            let label = d.path.split('/').filter(x => x !== '').pop();
            
            if (label === 'Archive') {
                label = d.category === 'Business' ? 'Biz_Archive' : 'Sys_Archive';
            } else if (label === 'Knowledge_Base') {
                label = d.category === 'Business' ? 'Biz_KB' : 'Pers_KB';
            }
            basePaths[d.path] = { label: `${emoji} ${label}`, color: c };
        }
    });

    globalFlatDests.forEach(d => {
        let label = d.path.split('/').filter(x => x !== '').pop();
        let color = '#949ba4';
        let emoji = '📁';
        
        if (d.path === 'DELETE') {
            label = 'Delete';
            emoji = '🗑';
            color = '#ff5252';
        } else if (d.path === '~/_Quarantine/To_Review' || d.path === 'To_Review') {
            label = 'Review';
            emoji = '❓';
            color = '#ffd740';
        } else if (d.category === 'System' || d.path.includes('Archive')) {
            emoji = '📦';
            color = '#b388ff';
        } else if (d.category === 'Business') {
            emoji = '💼';
            color = '#448aff';
        } else if (d.category === 'Personal') {
            emoji = '🏠';
            color = '#69f0ae';
        } else if (d.category === 'AI') {
            emoji = '🤖';
            color = '#e040fb';
        }
        
        if (label === 'Archive') {
            label = d.category === 'Business' ? 'Biz_Archive' : 'Sys_Archive';
        } else if (label === 'Knowledge_Base') {
            label = d.category === 'Business' ? 'Biz_KB' : 'Pers_KB';
        }
        
        let finalLabel = `${emoji} ${label}`;
        
        if (d.category === 'Custom') {
            color = '#ffffff';
            let longestMatch = '';
            for (const bp of Object.keys(basePaths)) {
                if (d.path.startsWith(bp + '/') && bp.length > longestMatch.length) {
                    longestMatch = bp;
                }
            }
            if (longestMatch) {
                const pInfo = basePaths[longestMatch];
                const subPath = d.path.substring(longestMatch.length + 1);
                finalLabel = `↳ ${subPath}`;
                color = pInfo.color;
            } else {
                finalLabel = `📁 ${label}`;
            }
        }
        
        dynamicActions.push({
            id: d.path,
            label: finalLabel,
            category: d.category,
            color: color
        });
    });

    const sortedActions = [];
    
    const prio = dynamicActions.filter(a => a.id === 'DELETE' || a.id === '~/_Quarantine/To_Review' || a.id === 'To_Review');
    prio.forEach(a => sortedActions.push(a));
    
    const baseActions = dynamicActions.filter(a => a.category !== 'Custom' && a.id !== 'DELETE' && !a.id.includes('To_Review'));
    const customActions = dynamicActions.filter(a => a.category === 'Custom');
    
    baseActions.forEach(ba => {
        sortedActions.push(ba);
        const children = customActions.filter(ca => ca.id.startsWith(ba.id + '/'));
        children.sort((a, b) => a.id.localeCompare(b.id));
        children.forEach(ca => {
            sortedActions.push(ca);
            const idx = customActions.indexOf(ca);
            if (idx > -1) customActions.splice(idx, 1);
        });
    });
    
    customActions.forEach(ca => sortedActions.push(ca));
    
    dynamicActions = sortedActions;
}

async function saveDestinationsToAPI() {
    try {
        const res = await fetch('/api/save_destinations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(destinations)
        });
        if (!res.ok) {
            const errText = await res.text();
            throw new Error(`Server returned ${res.status}: ${errText}`);
        }
        console.log("Folders configuration saved!");
    } catch (e) {
        console.error("Failed to save destinations", e);
        alert("Server Error: " + e.message);
    }
}

function saveProgress() {
    const progress = {};
    globalFiles.forEach(f => {
        if (f.current_dest !== f.original_dest || f.selected || f.is_dir_move || f.reviewed) {
            progress[f.id] = {
                current_dest: f.current_dest,
                selected: f.selected,
                is_dir_move: f.is_dir_move,
                parent_dir_to_move: f.parent_dir_to_move,
                reviewed: f.reviewed
            };
        }
    });
    localStorage.setItem('macCleanerProgress', JSON.stringify(progress));
}

function setupBulkBarOptions() {
    const tagsContainer = document.getElementById('bulk-tags');
    let tagsHtml = '';
    dynamicActions.forEach(qa => {
        tagsHtml += `
            <label class="tag-label" style="--tag-color: ${qa.color}">
                <input type="radio" name="bulk_dest" value="${qa.id}" class="quick-radio">
                <span class="tag-text">${qa.label}</span>
            </label>
        `;
    });
    tagsHtml += `
        <button id="btn-bulk-custom" class="filter-btn btn-custom" style="margin-left: 0.5rem; padding: 0.2rem 0.5rem; font-size: 0.8rem;">✍️ Custom...</button>
    `;
    tagsContainer.innerHTML = tagsHtml;
    
    document.getElementById('btn-bulk-custom').addEventListener('click', () => {
        const dest = prompt("Enter custom folder name (e.g. '~/Documents/Reports'):");
        if (dest && dest.trim() !== '') {
            globalFiles.forEach(f => {
                if (f.selected) {
                    f.current_dest = dest.trim();
                    f.selected = false;
                    f.reviewed = true;
                }
            });
            const bulkRadios = document.querySelectorAll('#bulk-tags .quick-radio');
            bulkRadios.forEach(r => r.checked = false);
            renderUI();
            saveProgress();
        }
    });
}

function updateBulkBarVisibility() {
    const selectedCount = globalFiles.filter(f => f.selected).length;
    const bulkBar = document.getElementById('bulk-bar');
    const countEl = document.getElementById('bulk-count');
    
    countEl.innerText = selectedCount;
    
    if (selectedCount > 0) {
        bulkBar.classList.remove('hidden');
    } else {
        bulkBar.classList.add('hidden');
    }
}

function renderUI() {
    renderFilters();
    renderGroupedList();
    updateBulkBarVisibility();
    
    updateProgressStats();
}

function updateProgressStats() {
    const totalFiles = globalFiles.length;
    
    const statsTotal = document.getElementById('stats-total');
    if (statsTotal) {
        statsTotal.innerText = totalFiles + ' files';
    }
    
    if (totalFiles === 0) return;
    
    // Count protected files (excluded from progress)
    const protectedCount = globalFiles.filter(f => 
        f.protection === 'system' || f.protection === 'app_storage' || f.is_icloud_stub
    ).length;
    const sortableFiles = totalFiles - protectedCount;
    
    let organizedCount = 0;
    globalFiles.forEach(f => {
        // Skip protected files in progress calculation
        if (f.protection === 'system' || f.protection === 'app_storage' || f.is_icloud_stub) return;
        if (f.current_dest !== f.original_dest || f.reviewed || f.is_dir_move || f.current_dest === 'DELETE') {
            organizedCount++;
        }
    });
    
    const percent = sortableFiles > 0 ? Math.round((organizedCount / sortableFiles) * 100) : 0;
    
    const bar = document.getElementById('progress-bar');
    const textPercent = document.getElementById('progress-text');
    const textStats = document.getElementById('stats-text');
    
    if (bar) bar.style.width = `${percent}%`;
    if (textPercent) textPercent.innerText = `${percent}%`;
    if (textStats) {
        let statsText = `${organizedCount} / ${sortableFiles} files organized`;
        if (protectedCount > 0) {
            statsText += ` (${protectedCount} protected)`;
        }
        textStats.innerText = statsText;
    }
}

function getShortDestName(path) {
    const qa = dynamicActions.find(q => q.id === path);
    if (qa) return qa.label;
    if (path.includes('/')) return '📂 ' + path.split('/').pop();
    return path;
}

function renderFilters() {
    const filterBar = document.getElementById('filter-bar');
    
    const counts = { 'ALL': globalFiles.length };
    let unsortedCount = 0;
    
    globalFiles.forEach(f => {
        const key = viewMode === 'SOURCE' ? f.original_dest : f.current_dest;
        counts[key] = (counts[key] || 0) + 1;
        
        const isProtected = f.protection === 'system' || f.protection === 'app_storage' || f.is_icloud_stub;
        if (!f.reviewed && f.current_dest === f.original_dest && !f.is_dir_move && !isProtected) {
            unsortedCount++;
        }
    });
    
    let html = `<button class="filter-btn ${currentFilter === 'ALL' ? 'active' : ''}" data-group="ALL">All Folders (${counts['ALL']})</button>`;
    html += `<button class="filter-btn ${currentFilter === 'UNSORTED' ? 'active' : ''}" data-group="UNSORTED" style="color: #ffb74d; border-color: #ffb74d;">To Do (${unsortedCount})</button>`;
    
    Object.keys(counts).forEach(dest => {
        if (dest === 'ALL') return;
        const isActive = currentFilter === dest ? 'active' : '';
        html += `<button class="filter-btn ${isActive}" data-group="${dest}">${getShortDestName(dest)} (${counts[dest]})</button>`;
    });
    
    filterBar.innerHTML = html;
    
    filterBar.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            currentFilter = e.target.dataset.group;
            
            filterBar.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            
            // Re-render the list entirely because groups and items change based on filter
            renderGroupedList();
        });
    });
}

function renderGroupedList() {
    const listEl = document.getElementById('file-list');
    listEl.innerHTML = '';
    
    const groups = {};
    globalFiles.forEach(f => {
        const key = viewMode === 'SOURCE' ? f.original_dest : f.current_dest;
        if (!groups[key]) groups[key] = [];
        groups[key].push(f);
    });
    
    // Сортировка ключей для DEST режима, чтобы папки были упорядочены
    let sortedKeys = Object.keys(groups);
    if (viewMode === 'DEST') {
        sortedKeys.sort();
    }
    
    for (const dest of sortedKeys) {
        const groupFiles = groups[dest];
        // Ignore group filter if we are actively searching
        if (!searchQuery && currentFilter !== 'ALL' && currentFilter !== 'UNSORTED' && currentFilter !== dest) continue;
        
        let visibleGroupFiles = groupFiles;
        
        // Apply search filter if query exists
        if (searchQuery) {
            visibleGroupFiles = visibleGroupFiles.filter(f => {
                return f.filename.toLowerCase().includes(searchQuery) || f.path.toLowerCase().includes(searchQuery);
            });
            if (visibleGroupFiles.length === 0) continue;
        }
        
        if (currentFilter === 'UNSORTED') {
            visibleGroupFiles = groupFiles.filter(f => {
                const isProtected = f.protection === 'system' || f.protection === 'app_storage' || f.is_icloud_stub;
                return !f.reviewed && f.current_dest === f.original_dest && !f.is_dir_move && !isProtected;
            });
            if (visibleGroupFiles.length === 0) continue;
        }
        
        const isAllSelected = visibleGroupFiles.length > 0 && visibleGroupFiles.every(f => f.selected);
        
        const groupEl = document.createElement('div');
        groupEl.className = 'group-container';
        groupEl.dataset.dest = dest;
        
        let html = `
            <div class="group-header">
                <input type="checkbox" class="group-checkbox" data-dest="${dest}" ${isAllSelected ? 'checked' : ''}>
                <div class="group-title">${getShortDestName(dest)} <span class="group-count">${visibleGroupFiles.length}</span></div>
            </div>
            <div class="group-files">
        `;
        
        const limit = groupLimits[dest] || 50;
        const visibleFiles = visibleGroupFiles.slice(0, limit);
        
        visibleFiles.forEach(file => {
            // === PROTECTION CHECK ===
            const isProtected = file.protection === 'system' || file.protection === 'app_storage' || file.is_icloud_stub;
            const isDevProject = file.protection === 'dev_project';
            
            let protectionBadge = '';
            if (file.protection === 'system') {
                protectionBadge = '<span class="badge" style="background: rgba(255,82,82,0.2); color: #ff5252; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 0.5rem;">🔒 System File</span>';
            } else if (file.protection === 'app_storage') {
                protectionBadge = '<span class="badge" style="background: rgba(255,183,77,0.2); color: #ffb74d; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 0.5rem;">📦 App Storage — На разбор</span>';
            } else if (isDevProject) {
                protectionBadge = `<span class="badge" style="background: rgba(68,138,255,0.2); color: #448aff; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 0.5rem;">🔧 Project: ${file.atomic_project || 'Dev'}</span>`;
            }
            if (file.is_icloud_stub) {
                protectionBadge = '<span class="badge" style="background: rgba(255,235,59,0.2); color: #ffeb3b; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 0.5rem;">☁️ iCloud Only</span>';
            }
            if (file.is_locked_by_process) {
                protectionBadge += `<span class="badge" style="background: rgba(255,82,82,0.15); color: #ff5252; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 0.5rem;">🔴 Used by: ${file.locked_by || 'process'}</span>`;
            }
            if (file.has_alias) {
                protectionBadge += '<span class="badge" style="background: rgba(171,71,188,0.2); color: #ab47bc; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 0.5rem;">🔗 Has Alias</span>';
            }
            
            let badge = '';
            let targetPathHtml = '';
            const isReassigned = file.current_dest !== file.original_dest;
            const reassignedClass = isReassigned ? 'reassigned' : '';
            
            if (!isProtected) {
                if (file.current_dest) {
                    if (file.current_dest === 'DELETE') {
                        badge = '<span class="badge badge-delete">Delete</span>';
                    } else if (file.current_dest === '~/_Quarantine/To_Review' || file.current_dest === 'To_Review') {
                        if (isReassigned || file.reviewed) {
                            badge = '<span class="badge badge-review">Review</span>';
                        }
                    } else {
                        if (isReassigned || file.reviewed) {
                            badge = '<span class="badge badge-move">Move</span>';
                        }
                    }
                }
                
                // Скрываем бэйджи цели, если мы уже находимся в режиме группировки по цели
                if (viewMode === 'SOURCE' && file.current_dest !== file.original_dest) {
                    targetPathHtml = `<div style="color: #69f0ae; font-size: 0.85rem; margin-top: 0.2rem;">↳ Target: ${file.current_dest}</div>`;
                } else if (viewMode === 'DEST') {
                    targetPathHtml = `<div style="color: #888; font-size: 0.85rem; margin-top: 0.2rem;">Исходный путь: ${file.original_dest}</div>`;
                }
                
                if (file.is_dir_move) {
                    badge += ' <span class="badge badge-dir" style="background: rgba(255, 183, 77, 0.2); color: #ffb74d; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; margin-left: 0.5rem;">📁 Dir Move</span>';
                }
            }
            
            // Build tags (action buttons)
            let tagsHtml = '';
            
            if (isProtected) {
                // Protected files: show protection reason, no action buttons
                tagsHtml = `<span style="color: #888; font-style: italic; font-size: 0.85rem;">${file.protection_reason || 'Protected file'} — не перемещается</span>`;
            } else if (isDevProject) {
                // Dev project files: only allow "Projects" destination or leave as-is
                tagsHtml = `<span style="color: #448aff; font-size: 0.85rem;">🔧 Проект переносится только целиком через <strong>Move Folder</strong></span>
                    <button class="filter-btn btn-open" data-path="${file.path}" style="margin-left: 0.5rem; padding: 0.2rem 0.5rem; font-size: 0.8rem; border-color: #69f0ae; color: #69f0ae;">👁 View</button>
                    <button class="filter-btn btn-move-dir" data-id="${file.id}" style="margin-left: 0.5rem; padding: 0.2rem 0.5rem; font-size: 0.8rem; border-color: #ffb74d; color: #ffb74d;">📁 Move Folder...</button>
                `;
            } else {
                // Normal files: full action buttons
                const isKnown = dynamicActions.find(qa => qa.id === file.current_dest);
                
                dynamicActions.forEach(qa => {
                    const isSelected = (file.current_dest === qa.id) ? 'checked' : '';
                    tagsHtml += `
                        <label class="tag-label" style="--tag-color: ${qa.color}">
                            <input type="radio" name="dest_${file.id}" value="${qa.id}" class="quick-radio ind-radio" data-id="${file.id}" ${isSelected}>
                            <span class="tag-text">${qa.label}</span>
                        </label>
                    `;
                });
                
                if (!isKnown && file.current_dest && file.current_dest !== 'DELETE' && file.current_dest !== '~/_Quarantine/To_Review') {
                    let fallbackColor = '#ffffff';
                    let finalLabel = `📁 ${file.current_dest.split('/').filter(x => x !== '').pop()}`;
                    
                    let longestMatch = '';
                    for (const qa of dynamicActions) {
                        if (qa.category !== 'Custom' && file.current_dest.startsWith(qa.id + '/') && qa.id.length > longestMatch.length) {
                            longestMatch = qa.id;
                        }
                    }
                    
                    if (longestMatch) {
                        const qaBase = dynamicActions.find(q => q.id === longestMatch);
                        const subPath = file.current_dest.substring(longestMatch.length + 1);
                        finalLabel = `↳ ${subPath}`;
                        fallbackColor = qaBase.color;
                    }
                    
                     tagsHtml += `
                        <label class="tag-label" style="--tag-color: ${fallbackColor}">
                            <input type="radio" name="dest_${file.id}" value="${file.current_dest}" class="quick-radio ind-radio" data-id="${file.id}" checked>
                            <span class="tag-text">${finalLabel}</span>
                        </label>
                    `;
                }
                
                tagsHtml += `
                    <button class="filter-btn btn-ind-custom" data-id="${file.id}" style="margin-left: 0.5rem; padding: 0.2rem 0.5rem; font-size: 0.8rem;">✍️ Custom...</button>
                    <button class="filter-btn btn-subfolder" data-id="${file.id}" style="margin-left: 0.5rem; padding: 0.2rem 0.5rem; font-size: 0.8rem; border-color: #4db6ac; color: #4db6ac;">↳ Subfolder</button>
                    <button class="filter-btn btn-open" data-path="${file.path}" style="margin-left: 0.5rem; padding: 0.2rem 0.5rem; font-size: 0.8rem; border-color: #69f0ae; color: #69f0ae;">👁 View</button>
                    <button class="filter-btn btn-move-dir" data-id="${file.id}" style="margin-left: 0.5rem; padding: 0.2rem 0.5rem; font-size: 0.8rem; border-color: #ffb74d; color: #ffb74d;">📁 Move Folder...</button>
                `;
            }
            
            const descText = file.description || '<span style="color: #ff5252; font-style: italic;">No description</span>';
            const sizeMb = (file.size_bytes / 1024 / 1024).toFixed(2);
            
                const dirMoveClass = file.is_dir_move ? 'dir-move-row' : '';
                const protectedRowClass = isProtected ? 'protected-row' : '';
                html += `
                <div class="file-item ${reassignedClass} ${dirMoveClass} ${protectedRowClass}" data-id="${file.id}">
                    <div class="file-main-row">
                        <div class="col-checkbox"><input type="checkbox" class="file-checkbox" data-id="${file.id}" ${file.selected ? 'checked' : ''} ${isProtected ? 'disabled' : ''}></div>
                        <div class="col-file">
                            <div class="file-name">${file.filename} ${badge} ${protectionBadge}</div>
                            <div class="file-meta">${sizeMb} MB &middot; ${file.path}</div>
                            ${targetPathHtml}
                        </div>
                        <div class="col-desc">${descText}</div>
                    </div>
                    <div class="file-actions-row">
                        <div class="quick-tags" style="flex-wrap: wrap; gap: 0.4rem;">
                            ${tagsHtml}
                        </div>
                    </div>
                </div>
            `;
        });
        
        html += `</div>`;
        if (visibleGroupFiles.length > limit) {
            html += `<div class="load-more-container"><button class="filter-btn load-more-btn" data-dest="${dest}">Show more (${visibleGroupFiles.length - limit} left)</button></div>`;
        }
        
        groupEl.innerHTML = html;
        listEl.appendChild(groupEl);
    }
    
    attachEventListeners();
}

function attachEventListeners() {
    document.querySelectorAll('.file-checkbox').forEach(cb => {
        cb.addEventListener('change', (e) => {
            const id = e.target.dataset.id;
            const file = globalFiles.find(f => f.id === id);
            if (file) file.selected = e.target.checked;
            
            const groupEl = e.target.closest('.group-container');
            const groupCb = groupEl.querySelector('.group-checkbox');
            const allChecked = Array.from(groupEl.querySelectorAll('.file-checkbox')).every(c => c.checked);
            groupCb.checked = allChecked;
            
            updateBulkBarVisibility();
            saveProgress();
        });
    });
    
    document.querySelectorAll('.group-checkbox').forEach(cb => {
        cb.addEventListener('change', (e) => {
            const dest = e.target.dataset.dest;
            const isChecked = e.target.checked;
            
            globalFiles.forEach(f => {
                if (f.original_dest === dest) {
                    f.selected = isChecked;
                }
            });
            
            const groupEl = e.target.closest('.group-container');
            groupEl.querySelectorAll('.file-checkbox').forEach(c => c.checked = isChecked);
            
            updateBulkBarVisibility();
            saveProgress();
        });
    });
    
    document.querySelectorAll('.ind-radio').forEach(r => {
        r.addEventListener('change', (e) => {
            const id = e.target.dataset.id;
            const file = globalFiles.find(f => f.id === id);
            if (file) {
                file.current_dest = e.target.value;
                file.reviewed = true;
                
                // Исключение: отвязываем файл от массового переноса папки
                const wasDirMove = file.is_dir_move;
                file.is_dir_move = false;
                file.parent_dir_to_move = null;
                
                const fItem = e.target.closest('.file-item');
                updateVisualSoftAssignment(fItem, file);
                
                if (wasDirMove && fItem) {
                    fItem.classList.remove('dir-move-row');
                    const badge = fItem.querySelector('.badge-dir');
                    if (badge) badge.remove();
                }
                
                updateProgressStats();
                saveProgress();
                
                if (viewMode === 'DEST') {
                    renderUI();
                }
            }
        });
    });
    
    document.querySelectorAll('.btn-ind-custom').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.target.dataset.id;
            const file = globalFiles.find(f => f.id === id);
            if (file) {
                const originalText = btn.innerHTML;
                btn.innerHTML = '⏳...';
                
                try {
                    const res = await fetch('/api/choose_folder');
                    const data = await res.json();
                    
                    let finalPath = null;
                    
                    if (data.path) {
                        let baseFolder = data.path;
                        if (baseFolder.endsWith('/')) {
                            baseFolder = baseFolder.slice(0, -1);
                        }
                        const subFolder = prompt(`Base folder selected:\n${baseFolder}\n\nEnter new folder name to create inside (or leave empty to just use the base folder):`);
                        
                        if (subFolder !== null) {
                            if (subFolder.trim() !== '') {
                                finalPath = `${baseFolder}/${subFolder.trim()}`;
                            } else {
                                finalPath = baseFolder;
                            }
                        }
                    } else if (data.error === 'canceled') {
                        // user canceled, do nothing
                    } else {
                        const dest = prompt("Could not open native picker. Enter custom folder full path:");
                        if (dest && dest.trim() !== '') {
                            finalPath = dest.trim();
                        }
                    }
                    
                    if (finalPath) {
                        file.current_dest = finalPath;
                        file.reviewed = true;
                        file.is_dir_move = false;
                        file.parent_dir_to_move = null;
                        
                        let found = false;
                        for (const paths of Object.values(destinations)) {
                            if (paths.includes(finalPath)) {
                                found = true;
                                break;
                            }
                        }
                        
                        if (!found) {
                            if (!destinations['Custom']) {
                                destinations['Custom'] = [];
                            }
                            destinations['Custom'].push(finalPath);
                            globalFlatDests.push({category: 'Custom', path: finalPath});
                            buildDynamicActions();
                            await saveDestinationsToAPI();
                        }
                        
                        renderUI(); 
                        saveProgress();
                    }
                } catch (err) {
                    console.error(err);
                    alert("Error communicating with server.py. Fallback active.");
                    const dest = prompt("Enter custom folder full path:");
                    if (dest && dest.trim() !== '') {
                        file.current_dest = dest.trim();
                        renderUI();
                        saveProgress();
                    }
                } finally {
                    btn.innerHTML = originalText;
                }
            }
        });
    });
    
    document.querySelectorAll('.btn-open').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const path = e.target.dataset.path;
            fetch(`/api/open?path=${encodeURIComponent(path)}`).then(res => {
                if (!res.ok) alert("Failed to open file. Are you running server.py?");
            }).catch(err => {
                alert("Cannot connect to server. Please run: python3 server.py");
            });
        });
    });
    
    document.querySelectorAll('.btn-move-dir').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const id = e.target.dataset.id;
            const file = globalFiles.find(f => f.id === id);
            if (file) {
                if (file.current_dest === 'DELETE') {
                    alert("Cannot move folder tree to DELETE. Please select a valid folder first.");
                    return;
                }
                
                const modal = document.getElementById('dir-modal');
                const targetSpan = document.getElementById('dir-modal-target');
                const optionsContainer = document.getElementById('dir-modal-options');
                
                targetSpan.textContent = file.current_dest;
                optionsContainer.innerHTML = '';
                
                const parts = file.path.split('/');
                parts.pop(); // remove filename
                
                let currentPath = '';
                const ancestors = [];
                for (let i = 0; i < parts.length; i++) {
                    if (parts[i] !== '') {
                        currentPath += '/' + parts[i];
                        ancestors.push({ name: parts[i], path: currentPath });
                    }
                }
                
                ancestors.reverse();
                
                ancestors.forEach((anc, idx) => {
                    const rowDiv = document.createElement('div');
                    rowDiv.style = "display: flex; gap: 0.5rem; margin-bottom: 0.5rem;";
                    
                    const btnOption = document.createElement('button');
                    btnOption.className = 'dir-option-btn';
                    btnOption.style.flex = "1";
                    
                    let levelText = idx === 0 ? "(Current)" : `(${idx} up)`;
                    btnOption.innerHTML = `📁 <strong>${anc.name}</strong> <span style="color:#888; font-size: 0.8rem; float:right;">${levelText}</span>`;
                    
                    btnOption.onclick = () => {
                        let exceptionsCount = 0;
                        globalFiles.forEach(f => {
                            if (f.path.startsWith(anc.path + '/')) {
                                if (f.reviewed && !f.is_dir_move && f.current_dest !== file.current_dest) {
                                    exceptionsCount++;
                                }
                            }
                        });
                        
                        let overwriteExceptions = false;
                        if (exceptionsCount > 0) {
                            overwriteExceptions = confirm(`⚠️ Внимание! Внутри папки '${anc.name}' есть файлы (${exceptionsCount} шт), которые вы ранее распределили индивидуально в ДРУГИЕ папки.\n\nНажмите [OK] — чтобы переместить ВСЁ и перезаписать эти файлы.\nНажмите [Отмена] — чтобы переместить папку, но СОХРАНИТЬ ваши ручные исключения.`);
                        }
                        
                        globalFiles.forEach(f => {
                            if (f.path.startsWith(anc.path + '/')) {
                                const isException = (f.reviewed && !f.is_dir_move && f.current_dest !== file.current_dest);
                                if (isException && exceptionsCount > 0 && !overwriteExceptions) {
                                    // Пропускаем (оставляем исключение в покое)
                                    return;
                                }
                                f.current_dest = file.current_dest;
                                f.is_dir_move = true;
                                f.parent_dir_to_move = anc.path;
                                f.reviewed = true;
                            }
                        });
                        
                        modal.style.display = 'none';
                        renderUI();
                        saveProgress();
                    };
                    
                    const btnUndo = document.createElement('button');
                    btnUndo.className = 'dir-undo-btn';
                    btnUndo.title = 'Undo Dir Move for this folder';
                    btnUndo.innerHTML = '❌';
                    btnUndo.onclick = () => {
                        if (confirm(`Are you sure you want to revert all files in ${anc.name} to their original state?`)) {
                            globalFiles.forEach(f => {
                                if (f.path.startsWith(anc.path + '/')) {
                                    f.current_dest = f.original_dest;
                                    f.is_dir_move = false;
                                    f.parent_dir_to_move = null;
                                    f.reviewed = false;
                                }
                            });
                            modal.style.display = 'none';
                            renderUI();
                            saveProgress();
                        }
                    };
                    
                    rowDiv.appendChild(btnOption);
                    rowDiv.appendChild(btnUndo);
                    optionsContainer.appendChild(rowDiv);
                });
                
                // Popover positioning
                const rect = btn.getBoundingClientRect();
                modal.style.top = `${rect.bottom + window.scrollY + 8}px`;
                let leftPos = rect.left + window.scrollX - 150; // Align nicely with button
                if (leftPos < 10) leftPos = 10;
                modal.style.left = `${leftPos}px`;
                
                modal.style.display = 'block';
                
                document.getElementById('dir-modal-cancel').onclick = () => {
                    modal.style.display = 'none';
                };
            }
        });
    });
    
    document.querySelectorAll('.btn-subfolder').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.target.dataset.id;
            const file = globalFiles.find(f => f.id === id);
            if (file) {
                if (!file.current_dest || file.current_dest === 'DELETE' || file.current_dest === 'To_Review') {
                    alert("Please select a valid base folder (e.g. Projects) for this file first.");
                    return;
                }
                
                const baseFolder = file.current_dest;
                const subFolderName = prompt(`Base folder is:\n${baseFolder}\n\nEnter name for the NEW subfolder:`);
                
                if (subFolderName !== null && subFolderName.trim() !== '') {
                    let finalPath = baseFolder;
                    if (finalPath.endsWith('/')) {
                        finalPath = finalPath.slice(0, -1);
                    }
                    finalPath += '/' + subFolderName.trim();
                    
                    file.current_dest = finalPath;
                    file.reviewed = true;
                    file.is_dir_move = false;
                    file.parent_dir_to_move = null;
                    
                    let found = false;
                    for (const paths of Object.values(destinations)) {
                        if (paths.includes(finalPath)) {
                            found = true;
                            break;
                        }
                    }
                    
                    if (!found) {
                        if (!destinations['Custom']) {
                            destinations['Custom'] = [];
                        }
                        destinations['Custom'].push(finalPath);
                        globalFlatDests.push({category: 'Custom', path: finalPath});
                        buildDynamicActions();
                        await saveDestinationsToAPI();
                    }
                    
                    renderUI(); 
                    saveProgress();
                }
            }
        });
    });
    
    document.getElementById('btn-manage-folders').addEventListener('click', () => {
        const modal = document.getElementById('manage-folders-modal');
        const listDiv = document.getElementById('manage-folders-list');
        listDiv.innerHTML = '';
        
        for (const [category, paths] of Object.entries(destinations)) {
            const catHeader = document.createElement('div');
            catHeader.className = 'manage-folder-cat';
            catHeader.textContent = category;
            listDiv.appendChild(catHeader);
            
            paths.forEach((p, idx) => {
                const itemDiv = document.createElement('div');
                itemDiv.className = 'manage-folder-item';
                
                const span = document.createElement('span');
                span.textContent = p;
                
                const delBtn = document.createElement('button');
                delBtn.className = 'btn-delete-folder';
                delBtn.innerHTML = '🗑';
                delBtn.onclick = async () => {
                    if (confirm(`Remove folder "${p}"?`)) {
                        destinations[category].splice(idx, 1);
                        if (destinations[category].length === 0) {
                            delete destinations[category];
                        }
                        itemDiv.remove();
                        buildDynamicActions();
                        await saveDestinationsToAPI();
                        renderUI();
                    }
                };
                
                itemDiv.appendChild(span);
                itemDiv.appendChild(delBtn);
                listDiv.appendChild(itemDiv);
            });
        }
        
        modal.style.display = 'flex';
    });
    
    document.getElementById('btn-close-manage').addEventListener('click', () => {
        document.getElementById('manage-folders-modal').style.display = 'none';
    });
    
    document.querySelectorAll('.load-more-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const dest = e.target.dataset.dest;
            groupLimits[dest] = (groupLimits[dest] || 50) + 100;
            renderUI();
        });
    });
}

function updateVisualSoftAssignment(fileItem, file) {
    let targetDiv = fileItem.querySelector('.target-path-display');
    if (!targetDiv) {
        const fileMeta = fileItem.querySelector('.file-meta');
        if (fileMeta) {
            targetDiv = document.createElement('div');
            targetDiv.className = 'target-path-display file-meta';
            targetDiv.style = 'color: #69f0ae; margin-top: 0.3rem;';
            fileMeta.parentNode.insertBefore(targetDiv, fileMeta.nextSibling);
        }
    }
    
    if (file.current_dest && file.current_dest !== 'DELETE' && file.current_dest !== '~/_Quarantine/To_Review') {
        if (targetDiv) {
            if (file.current_dest !== file.original_dest || file.reviewed) {
                targetDiv.style.display = 'block';
                targetDiv.innerHTML = `↳ <strong>Target:</strong> ${file.current_dest}`;
            } else {
                targetDiv.style.display = 'none';
            }
        }
    } else {
        if (targetDiv) targetDiv.style.display = 'none';
    }
    
    let badgeSpan = fileItem.querySelector('.badge-move, .badge-delete, .badge-review');
    if (!badgeSpan) {
        const nameDiv = fileItem.querySelector('.file-name');
        if (nameDiv) {
            badgeSpan = document.createElement('span');
            nameDiv.appendChild(badgeSpan);
        }
    }
    
    if (badgeSpan) {
        if (file.current_dest === 'DELETE') {
            badgeSpan.className = 'badge badge-delete';
            badgeSpan.innerText = 'Delete';
        } else if (file.current_dest === '~/_Quarantine/To_Review' || file.current_dest === 'To_Review') {
            badgeSpan.className = 'badge badge-review';
            badgeSpan.innerText = 'Review';
        } else {
            badgeSpan.className = 'badge badge-move';
            badgeSpan.innerText = 'Move';
        }
    }

    if (file.current_dest !== file.original_dest) {
        fileItem.classList.add('reassigned');
    } else {
        fileItem.classList.remove('reassigned');
    }
}
