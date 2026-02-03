#!/usr/bin/env node
/**
 * parse_claude_export.js
 * 
 * Parses the official Claude export and extracts chats belonging to project "save"
 * Then bundles them with ./creati into a single agent-ready file.
 */

const fs = require('fs');
const path = require('path');
const mammoth = require('mammoth');

// ============================================================================
// CONFIGURATION
// ============================================================================
const BASE_DIR = path.resolve(__dirname, '..');
const EXPORT_DIR = path.join(BASE_DIR, 'saved', 'claude_export');
const OUTPUT_CHATS_DIR = path.join(BASE_DIR, 'saved', 'claude_web_chats', 'save');
const BUNDLES_DIR = path.join(BASE_DIR, 'saved', 'bundles');
const CREATI_DIR = path.join(BASE_DIR, 'creati');
const DOWNLOADS_DIR = path.join(require('os').homedir(), 'Downloads');

const TARGET_PROJECT_NAME = 'save';

// Additional DOCX files to include
const ADDITIONAL_DOCX_FILES = [
    'surgents file .docx',
    'closepd loop code openw orld .docx',
    'LOCKED ROOM RIGHT(impact.docx',
    'theology.docx'
];

// ============================================================================
// UTILITIES
// ============================================================================
function ensureDir(dirPath) {
    if (!fs.existsSync(dirPath)) {
        fs.mkdirSync(dirPath, { recursive: true });
        console.log(`[+] Created directory: ${dirPath}`);
    }
}

function sanitizeFilename(name) {
    return name
        .replace(/[<>:"/\\|?*]/g, '_')
        .replace(/\s+/g, '_')
        .replace(/_+/g, '_')
        .substring(0, 100);
}

function formatRole(role) {
    switch (role) {
        case 'human': return 'USER';
        case 'assistant': return 'ASSISTANT';
        case 'system': return 'SYSTEM';
        default: return role.toUpperCase();
    }
}

function extractTextFromContent(content) {
    if (typeof content === 'string') {
        return content;
    }
    if (Array.isArray(content)) {
        return content
            .filter(item => item.type === 'text' && item.text)
            .map(item => item.text)
            .join('\n\n');
    }
    if (content && typeof content === 'object' && content.text) {
        return content.text;
    }
    return '';
}

// ============================================================================
// MAIN LOGIC
// ============================================================================
async function main() {
    console.log('='.repeat(60));
    console.log('CLAUDE EXPORT PARSER - Project: "save"');
    console.log('='.repeat(60));
    console.log();

    // Step 1: Ensure output directories exist
    ensureDir(OUTPUT_CHATS_DIR);
    ensureDir(BUNDLES_DIR);

    // Step 2: Locate and read projects.json to find "save" project UUID
    const projectsFile = path.join(EXPORT_DIR, 'projects.json');
    if (!fs.existsSync(projectsFile)) {
        console.error('[FATAL] projects.json not found at:', projectsFile);
        process.exit(1);
    }

    console.log('[*] Reading projects.json...');
    const projectsData = JSON.parse(fs.readFileSync(projectsFile, 'utf-8'));
    
    const saveProject = projectsData.find(
        p => p.name && p.name.toLowerCase() === TARGET_PROJECT_NAME.toLowerCase()
    );

    if (!saveProject) {
        console.error(`[FATAL] Project "${TARGET_PROJECT_NAME}" not found in export!`);
        console.error('Available projects:', projectsData.map(p => p.name).join(', '));
        process.exit(1);
    }

    const saveProjectUUID = saveProject.uuid;
    const saveProjectCreatedAt = saveProject.created_at || saveProject.updated_at;
    console.log(`[+] Found project "${TARGET_PROJECT_NAME}" with UUID: ${saveProjectUUID}`);
    console.log(`[+] Project created at: ${saveProjectCreatedAt}`);

    // Find the next project created after "save" to determine the time window
    const sortedProjects = projectsData
        .filter(p => p.created_at)
        .sort((a, b) => a.created_at.localeCompare(b.created_at));
    
    const saveIndex = sortedProjects.findIndex(p => p.uuid === saveProjectUUID);
    const nextProject = sortedProjects[saveIndex + 1];
    const endTimestamp = nextProject ? nextProject.created_at : '9999-12-31T23:59:59';
    
    console.log(`[+] Next project: ${nextProject ? nextProject.name : 'none'} at ${nextProject ? nextProject.created_at : 'N/A'}`);
    console.log(`[+] Will match conversations updated between ${saveProjectCreatedAt.substring(0, 19)} and ${endTimestamp.substring(0, 19)}`);

    // Step 3: Read conversations.json and filter by project
    const conversationsFile = path.join(EXPORT_DIR, 'conversations.json');
    if (!fs.existsSync(conversationsFile)) {
        console.error('[FATAL] conversations.json not found at:', conversationsFile);
        process.exit(1);
    }

    console.log('[*] Reading conversations.json (this may take a moment)...');
    const fileContent = fs.readFileSync(conversationsFile, 'utf-8');
    console.log(`[*] File size: ${(fileContent.length / 1024 / 1024).toFixed(2)} MB`);
    
    const conversations = JSON.parse(fileContent);
    console.log(`[*] Total conversations in export: ${conversations.length}`);

    // Filter conversations belonging to "save" project
    // Claude's export doesn't have explicit project_uuid in conversations.
    // Instead, when chats are added to a project, their updated_at falls within the project's time window.
    const saveConversations = conversations.filter(conv => {
        // Match by updated_at timestamp (when added to project) - within the time window
        if (conv.updated_at && conv.updated_at >= saveProjectCreatedAt && conv.updated_at < endTimestamp) {
            return true;
        }
        // Also check if project_uuid exists (in case format changes)
        if (conv.project_uuid === saveProjectUUID) {
            return true;
        }
        return false;
    });
    
    if (saveConversations.length === 0) {
        console.error(`[FATAL] No conversations found for project "${TARGET_PROJECT_NAME}"!`);
        process.exit(1);
    }

    console.log(`[+] Found ${saveConversations.length} conversations in project "${TARGET_PROJECT_NAME}"`);
    console.log();

    // Step 4: Process each conversation and save as Markdown
    const savedFiles = [];
    let chatIndex = 1;

    for (const conv of saveConversations) {
        const title = conv.name || conv.title || `Untitled_${conv.uuid.substring(0, 8)}`;
        const sanitizedTitle = sanitizeFilename(title);
        const filename = `${String(chatIndex).padStart(2, '0')}_${sanitizedTitle}.md`;
        const filepath = path.join(OUTPUT_CHATS_DIR, filename);

        // Build markdown content
        let markdown = `# ${title}\n\n`;
        markdown += `**UUID:** ${conv.uuid}\n`;
        markdown += `**Created:** ${conv.created_at || 'Unknown'}\n`;
        markdown += `**Updated:** ${conv.updated_at || 'Unknown'}\n\n`;
        markdown += `---\n\n`;

        // Process chat messages
        const chatMessages = conv.chat_messages || [];
        for (const msg of chatMessages) {
            const role = formatRole(msg.sender || msg.role || 'unknown');
            const text = extractTextFromContent(msg.content || msg.text || '');
            
            if (text.trim()) {
                markdown += `## ${role}\n\n`;
                markdown += `${text}\n\n`;
            }
        }

        fs.writeFileSync(filepath, markdown, 'utf-8');
        savedFiles.push(filepath);
        console.log(`[+] Saved: ${filename}`);
        chatIndex++;
    }

    console.log();
    console.log(`[+] Extracted ${savedFiles.length} chats to ${OUTPUT_CHATS_DIR}`);

    // Step 5: Create save_chats.md bundle
    console.log();
    console.log('[*] Creating bundles...');

    const saveChatsBundle = path.join(BUNDLES_DIR, 'save_chats.md');
    let saveChatsConcatenated = `# Claude Chats - Project "save"\n\n`;
    saveChatsConcatenated += `**Total Chats:** ${savedFiles.length}\n`;
    saveChatsConcatenated += `**Generated:** ${new Date().toISOString()}\n\n`;
    saveChatsConcatenated += `---\n\n`;

    for (const file of savedFiles) {
        const content = fs.readFileSync(file, 'utf-8');
        saveChatsConcatenated += content;
        saveChatsConcatenated += '\n\n---\n\n';
    }

    fs.writeFileSync(saveChatsBundle, saveChatsConcatenated, 'utf-8');
    console.log(`[+] Created: ${saveChatsBundle}`);

    // Step 6: Create creati_pack.md
    const creatiPackPath = path.join(BUNDLES_DIR, 'creati_pack.md');
    let creatiContent = '';

    if (fs.existsSync(CREATI_DIR)) {
        console.log('[*] Found ./creati directory, bundling contents...');
        creatiContent = `# Creati Pack\n\n`;
        creatiContent += `**Source:** ${CREATI_DIR}\n`;
        creatiContent += `**Generated:** ${new Date().toISOString()}\n\n`;
        creatiContent += `---\n\n`;

        const validExtensions = ['.md', '.txt', '.yaml', '.yml', '.json'];
        
        function walkDir(dir) {
            const files = [];
            const entries = fs.readdirSync(dir, { withFileTypes: true });
            for (const entry of entries) {
                const fullPath = path.join(dir, entry.name);
                if (entry.isDirectory()) {
                    files.push(...walkDir(fullPath));
                } else if (validExtensions.includes(path.extname(entry.name).toLowerCase())) {
                    files.push(fullPath);
                }
            }
            return files;
        }

        const creatiFiles = walkDir(CREATI_DIR);
        console.log(`[*] Found ${creatiFiles.length} files in creati/`);

        for (const file of creatiFiles) {
            const relativePath = path.relative(BASE_DIR, file);
            const content = fs.readFileSync(file, 'utf-8');
            creatiContent += `## File: ${relativePath}\n\n`;
            creatiContent += '```\n';
            creatiContent += content;
            creatiContent += '\n```\n\n';
        }
    } else {
        console.log('[!] ./creati directory not found, creating notice...');
        creatiContent = `# Creati Pack\n\n`;
        creatiContent += `**Notice:** The ./creati directory was not found.\n\n`;
        creatiContent += `This bundle would typically contain creative assets and templates.\n`;
    }

    fs.writeFileSync(creatiPackPath, creatiContent, 'utf-8');
    console.log(`[+] Created: ${creatiPackPath}`);

    // Step 6.5: Process additional DOCX files
    console.log();
    console.log('[*] Processing additional DOCX files...');
    const additionalDocsPath = path.join(BUNDLES_DIR, 'additional_docs.md');
    let additionalContent = `# Additional Documents\n\n`;
    additionalContent += `**Source:** User's Downloads folder\n`;
    additionalContent += `**Generated:** ${new Date().toISOString()}\n\n`;
    additionalContent += `---\n\n`;

    for (const docxFile of ADDITIONAL_DOCX_FILES) {
        const docxPath = path.join(DOWNLOADS_DIR, docxFile);
        
        if (fs.existsSync(docxPath)) {
            try {
                console.log(`[*] Converting: ${docxFile}`);
                const result = await mammoth.extractRawText({ path: docxPath });
                const text = result.value;
                
                additionalContent += `## ${docxFile}\n\n`;
                additionalContent += `**File:** ${docxFile}\n`;
                additionalContent += `**Path:** ${docxPath}\n\n`;
                additionalContent += `### Content:\n\n`;
                additionalContent += text;
                additionalContent += `\n\n---\n\n`;
                
                console.log(`[+] Converted: ${docxFile} (${text.length} chars)`);
            } catch (err) {
                console.warn(`[!] Failed to convert ${docxFile}: ${err.message}`);
                additionalContent += `## ${docxFile}\n\n`;
                additionalContent += `**Error:** Failed to convert - ${err.message}\n\n`;
                additionalContent += `---\n\n`;
            }
        } else {
            console.warn(`[!] File not found: ${docxPath}`);
            additionalContent += `## ${docxFile}\n\n`;
            additionalContent += `**Status:** File not found at ${docxPath}\n\n`;
            additionalContent += `---\n\n`;
        }
    }

    fs.writeFileSync(additionalDocsPath, additionalContent, 'utf-8');
    console.log(`[+] Created: ${additionalDocsPath}`);

    // Step 7: Create final_agent_bundle.md
    const finalBundlePath = path.join(BUNDLES_DIR, 'final_agent_bundle.md');
    const creatiPack = fs.readFileSync(creatiPackPath, 'utf-8');
    const additionalDocs = fs.readFileSync(additionalDocsPath, 'utf-8');
    const saveChats = fs.readFileSync(saveChatsBundle, 'utf-8');

    const finalBundle = `${creatiPack}\n\n---\n\n${additionalDocs}\n\n---\n\n${saveChats}`;
    fs.writeFileSync(finalBundlePath, finalBundle, 'utf-8');
    console.log(`[+] Created: ${finalBundlePath}`);

    // Step 8: Print summary
    console.log();
    console.log('='.repeat(60));
    console.log('EXECUTION COMPLETE');
    console.log('='.repeat(60));
    console.log();
    console.log('SUMMARY:');
    console.log(`  - Project filter: "${TARGET_PROJECT_NAME}"`);
    console.log(`  - Chats extracted: ${savedFiles.length}`);
    console.log();
    console.log('OUTPUT FILES:');
    console.log(`  - Chat files: ${OUTPUT_CHATS_DIR}/`);
    savedFiles.forEach(f => console.log(`      - ${path.basename(f)}`));
    console.log();
    console.log('BUNDLES:');
    console.log(`  - ${saveChatsBundle}`);
    console.log(`  - ${creatiPackPath}`);
    console.log(`  - ${additionalDocsPath}`);
    console.log(`  - ${finalBundlePath}`);
    console.log();
    console.log('[SUCCESS] All deliverables created.');
}

main().catch(err => {
    console.error('[FATAL ERROR]', err);
    process.exit(1);
});
