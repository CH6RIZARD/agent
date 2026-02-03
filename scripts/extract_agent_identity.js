#!/usr/bin/env node
/**
 * extract_agent_identity.js
 * 
 * Extracts identity data from Claude chats and DOCX files.
 * RAW extraction - no sanitization, no moderation.
 */

const fs = require('fs');
const path = require('path');

// ============================================================================
// CONFIGURATION
// ============================================================================
const BASE_DIR = path.resolve(__dirname, '..');
const CHATS_DIR = path.join(BASE_DIR, 'saved', 'claude_web_chats', 'save');
const ADDITIONAL_DOCS = path.join(BASE_DIR, 'saved', 'bundles', 'additional_docs.md');
const OUTPUT_DIR = path.join(BASE_DIR, 'agent_source_data');

// ============================================================================
// UTILITIES
// ============================================================================
function ensureDir(dirPath) {
    if (!fs.existsSync(dirPath)) {
        fs.mkdirSync(dirPath, { recursive: true });
        console.log(`[+] Created directory: ${dirPath}`);
    }
}

function extractUserMessages(markdown) {
    const lines = markdown.split('\n');
    const messages = [];
    let currentRole = null;
    let currentMessage = [];
    
    for (const line of lines) {
        if (line.startsWith('## USER')) {
            if (currentRole === 'USER' && currentMessage.length > 0) {
                messages.push({ role: 'USER', content: currentMessage.join('\n').trim() });
            }
            currentRole = 'USER';
            currentMessage = [];
        } else if (line.startsWith('## ASSISTANT')) {
            if (currentRole === 'USER' && currentMessage.length > 0) {
                messages.push({ role: 'USER', content: currentMessage.join('\n').trim() });
            }
            currentRole = 'ASSISTANT';
            currentMessage = [];
        } else if (currentRole) {
            currentMessage.push(line);
        }
    }
    
    // Capture last message
    if (currentRole === 'USER' && currentMessage.length > 0) {
        messages.push({ role: 'USER', content: currentMessage.join('\n').trim() });
    }
    
    return messages.filter(m => m.role === 'USER' && m.content.length > 0);
}

function extractBeliefs(text) {
    const patterns = [
        /\b(I believe|I think|my belief|my view|the truth is|scripture says|Bible says|God says)\b/i,
        /\b(non-negotiable|core belief|fundamental|foundational)\b/i,
        /\b(will never|won't ever|refuse to)\b/i,
    ];
    
    const sentences = text.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 20);
    const matches = [];
    
    for (const sentence of sentences) {
        for (const pattern of patterns) {
            if (pattern.test(sentence)) {
                matches.push(sentence);
                break;
            }
        }
    }
    
    return matches;
}

function extractTheology(text) {
    const patterns = [
        /\b(devil|satan|demon|spiritual warfare|evil|wickedness)\b/i,
        /\b(God|Jesus|Christ|scripture|Bible|holy|prayer|sin)\b/i,
        /\b(deception|truth|lie|righteous|salvation|redemption)\b/i,
        /\b(Islamic|Muslim|Christian|theology|doctrine|faith)\b/i,
    ];
    
    const sentences = text.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 20);
    const matches = [];
    
    for (const sentence of sentences) {
        for (const pattern of patterns) {
            if (pattern.test(sentence)) {
                matches.push(sentence);
                break;
            }
        }
    }
    
    return matches;
}

function extractRedLines(text) {
    const patterns = [
        /\b(won't|will not|never|refuse to|can't|cannot|not going to)\b/i,
        /\b(red line|deal breaker|non-negotiable|unacceptable)\b/i,
    ];
    
    const sentences = text.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 20);
    const matches = [];
    
    for (const sentence of sentences) {
        for (const pattern of patterns) {
            if (pattern.test(sentence)) {
                matches.push(sentence);
                break;
            }
        }
    }
    
    return matches;
}

function extractWorkPatterns(text) {
    const patterns = [
        /\b(build|develop|create|design|implement|stack|tech|code)\b/i,
        /\b(approach|strategy|process|workflow|pattern|method)\b/i,
        /\b(project|product|feature|system|architecture)\b/i,
    ];
    
    const sentences = text.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 20);
    const matches = [];
    
    for (const sentence of sentences) {
        for (const pattern of patterns) {
            if (pattern.test(sentence)) {
                matches.push(sentence);
                break;
            }
        }
    }
    
    return matches;
}

function findStyleSamples(userMessages) {
    // Find longest, most unfiltered messages (rants, pushback, explanations)
    const candidates = userMessages
        .filter(m => m.content.length > 200)
        .map(m => ({
            content: m.content,
            length: m.content.length,
            intensity: (m.content.match(/[!?]/g) || []).length,
            profanity: (m.content.match(/\b(fuck|shit|damn|hell|wtf)\b/gi) || []).length,
        }))
        .sort((a, b) => (b.intensity + b.profanity + b.length / 100) - (a.intensity + a.profanity + a.length / 100));
    
    return candidates.slice(0, 3).map(c => c.content);
}

// ============================================================================
// MAIN LOGIC
// ============================================================================
async function main() {
    console.log('='.repeat(60));
    console.log('AGENT IDENTITY EXTRACTION');
    console.log('='.repeat(60));
    console.log();

    // Step 1: Create folder structure
    const conversationsDir = path.join(OUTPUT_DIR, 'conversations');
    const extractedDir = path.join(OUTPUT_DIR, 'extracted');
    
    ensureDir(OUTPUT_DIR);
    ensureDir(conversationsDir);
    ensureDir(extractedDir);

    // Step 2: Load all chat files
    console.log('[*] Loading chat files...');
    const chatFiles = fs.readdirSync(CHATS_DIR)
        .filter(f => f.endsWith('.md') && f !== '.gitkeep')
        .sort();
    
    console.log(`[+] Found ${chatFiles.length} chat files`);

    let allChatsContent = '';
    let allUserMessages = [];
    let totalMessages = 0;
    let dateRange = { earliest: null, latest: null };
    let topics = new Set();
    let projects = new Set();

    const constitutionRaw = [];
    const doctrineRaw = [];
    const theologicalStatements = [];
    const redLines = [];
    const workPatterns = [];

    // Step 3: Process each chat file
    for (const chatFile of chatFiles) {
        const chatPath = path.join(CHATS_DIR, chatFile);
        const content = fs.readFileSync(chatPath, 'utf-8');
        
        // Extract metadata from header
        const uuidMatch = content.match(/\*\*UUID:\*\* (.+)/);
        const createdMatch = content.match(/\*\*Created:\*\* (.+)/);
        const updatedMatch = content.match(/\*\*Updated:\*\* (.+)/);
        const titleMatch = content.match(/^# (.+)/m);
        
        const uuid = uuidMatch ? uuidMatch[1] : 'unknown';
        const created = createdMatch ? createdMatch[1] : 'unknown';
        const updated = updatedMatch ? updatedMatch[1] : 'unknown';
        const title = titleMatch ? titleMatch[1] : chatFile.replace('.md', '');
        
        // Track date range
        if (created !== 'unknown') {
            if (!dateRange.earliest || created < dateRange.earliest) {
                dateRange.earliest = created;
            }
            if (!dateRange.latest || created > dateRange.latest) {
                dateRange.latest = created;
            }
        }
        
        // Add to topics
        topics.add(title);
        
        // Extract project mentions
        const projectMatches = content.match(/\b(Scion|glasses|agent|AI|project|product|startup)\b/gi) || [];
        projectMatches.forEach(p => projects.add(p.toLowerCase()));
        
        // Add to all_chats.txt with clear separation
        allChatsContent += `\n${'='.repeat(80)}\n`;
        allChatsContent += `CHAT: ${title}\n`;
        allChatsContent += `UUID: ${uuid}\n`;
        allChatsContent += `CREATED: ${created}\n`;
        allChatsContent += `${'='.repeat(80)}\n\n`;
        
        // Extract messages
        const lines = content.split('\n');
        let currentRole = null;
        let currentMessage = [];
        
        for (const line of lines) {
            if (line.startsWith('## USER')) {
                if (currentMessage.length > 0) {
                    const msg = currentMessage.join('\n').trim();
                    if (msg) {
                        allChatsContent += `[${currentRole}]\n${msg}\n\n`;
                        if (currentRole === 'USER') {
                            totalMessages++;
                            allUserMessages.push({ title, content: msg });
                        }
                    }
                }
                currentRole = 'USER';
                currentMessage = [];
            } else if (line.startsWith('## ASSISTANT')) {
                if (currentMessage.length > 0) {
                    const msg = currentMessage.join('\n').trim();
                    if (msg) {
                        allChatsContent += `[${currentRole}]\n${msg}\n\n`;
                        if (currentRole === 'USER') {
                            totalMessages++;
                            allUserMessages.push({ title, content: msg });
                        }
                    }
                }
                currentRole = 'ASSISTANT';
                currentMessage = [];
            } else if (currentRole && !line.startsWith('**UUID:') && !line.startsWith('**Created:') && !line.startsWith('**Updated:') && !line.startsWith('---')) {
                currentMessage.push(line);
            }
        }
        
        // Capture last message
        if (currentMessage.length > 0) {
            const msg = currentMessage.join('\n').trim();
            if (msg) {
                allChatsContent += `[${currentRole}]\n${msg}\n\n`;
                if (currentRole === 'USER') {
                    totalMessages++;
                    allUserMessages.push({ title, content: msg });
                }
            }
        }
        
        // Extract patterns from USER messages only
        const userMessages = allUserMessages.map(m => m.content).join('\n\n');
        constitutionRaw.push(...extractBeliefs(userMessages));
        doctrineRaw.push(...extractBeliefs(userMessages));
        theologicalStatements.push(...extractTheology(userMessages));
        redLines.push(...extractRedLines(userMessages));
        workPatterns.push(...extractWorkPatterns(userMessages));
    }

    // Step 4: Add additional docs
    if (fs.existsSync(ADDITIONAL_DOCS)) {
        console.log('[*] Adding additional documents...');
        const additionalContent = fs.readFileSync(ADDITIONAL_DOCS, 'utf-8');
        
        allChatsContent += `\n${'='.repeat(80)}\n`;
        allChatsContent += `ADDITIONAL DOCUMENTS\n`;
        allChatsContent += `${'='.repeat(80)}\n\n`;
        allChatsContent += additionalContent;
        
        // Extract from additional docs too
        constitutionRaw.push(...extractBeliefs(additionalContent));
        doctrineRaw.push(...extractBeliefs(additionalContent));
        theologicalStatements.push(...extractTheology(additionalContent));
        redLines.push(...extractRedLines(additionalContent));
        workPatterns.push(...extractWorkPatterns(additionalContent));
    }

    // Step 5: Write all_chats.txt
    console.log('[*] Writing conversations/all_chats.txt...');
    const allChatsPath = path.join(conversationsDir, 'all_chats.txt');
    fs.writeFileSync(allChatsPath, allChatsContent, 'utf-8');
    console.log(`[+] Wrote ${allChatsContent.length} characters to all_chats.txt`);

    // Step 6: Write extracted files
    console.log('[*] Writing extracted files...');
    
    // Constitution
    const constitutionPath = path.join(extractedDir, 'constitution_raw.md');
    let constitutionContent = `# Constitution Raw\n\n`;
    constitutionContent += `**Extracted:** ${new Date().toISOString()}\n\n`;
    constitutionContent += `**Description:** Foundational beliefs, non-negotiables, core truths stated by the user.\n\n`;
    constitutionContent += `---\n\n`;
    [...new Set(constitutionRaw)].forEach((item, i) => {
        constitutionContent += `${i + 1}. ${item}\n\n`;
    });
    fs.writeFileSync(constitutionPath, constitutionContent, 'utf-8');
    console.log(`[+] Extracted ${[...new Set(constitutionRaw)].length} constitution items`);
    
    // Doctrine
    const doctrinePath = path.join(extractedDir, 'doctrine_raw.md');
    let doctrineContent = `# Doctrine Raw\n\n`;
    doctrineContent += `**Extracted:** ${new Date().toISOString()}\n\n`;
    doctrineContent += `**Description:** Decision-making rules, priorities, tradeoffs, how user operates.\n\n`;
    doctrineContent += `---\n\n`;
    [...new Set(doctrineRaw)].forEach((item, i) => {
        doctrineContent += `${i + 1}. ${item}\n\n`;
    });
    fs.writeFileSync(doctrinePath, doctrineContent, 'utf-8');
    console.log(`[+] Extracted ${[...new Set(doctrineRaw)].length} doctrine items`);
    
    // Style samples
    const stylePath = path.join(extractedDir, 'style_samples.txt');
    const styleSamples = findStyleSamples(allUserMessages);
    let styleContent = `STYLE SAMPLES\n\n`;
    styleContent += `Extracted: ${new Date().toISOString()}\n\n`;
    styleContent += `Description: Most unfiltered, characteristic user messages.\n\n`;
    styleContent += `${'='.repeat(80)}\n\n`;
    styleSamples.forEach((sample, i) => {
        styleContent += `SAMPLE ${i + 1}:\n\n${sample}\n\n${'='.repeat(80)}\n\n`;
    });
    fs.writeFileSync(stylePath, styleContent, 'utf-8');
    console.log(`[+] Extracted ${styleSamples.length} style samples`);
    
    // Theological statements
    const theologyPath = path.join(extractedDir, 'theological_statements.md');
    let theologyContent = `# Theological Statements\n\n`;
    theologyContent += `**Extracted:** ${new Date().toISOString()}\n\n`;
    theologyContent += `**Description:** Everything about devil, spiritual warfare, God, scripture, theology.\n\n`;
    theologyContent += `---\n\n`;
    [...new Set(theologicalStatements)].forEach((item, i) => {
        theologyContent += `${i + 1}. ${item}\n\n`;
    });
    fs.writeFileSync(theologyPath, theologyContent, 'utf-8');
    console.log(`[+] Extracted ${[...new Set(theologicalStatements)].length} theological statements`);
    
    // Red lines
    const redLinesPath = path.join(extractedDir, 'red_lines.md');
    let redLinesContent = `# Red Lines\n\n`;
    redLinesContent += `**Extracted:** ${new Date().toISOString()}\n\n`;
    redLinesContent += `**Description:** Things user won't do, won't compromise, won't say.\n\n`;
    redLinesContent += `---\n\n`;
    [...new Set(redLines)].forEach((item, i) => {
        redLinesContent += `${i + 1}. ${item}\n\n`;
    });
    fs.writeFileSync(redLinesPath, redLinesContent, 'utf-8');
    console.log(`[+] Extracted ${[...new Set(redLines)].length} red lines`);
    
    // Work patterns
    const workPath = path.join(extractedDir, 'work_patterns.md');
    let workContent = `# Work Patterns\n\n`;
    workContent += `**Extracted:** ${new Date().toISOString()}\n\n`;
    workContent += `**Description:** How user builds, tech stack, communication style, project approach.\n\n`;
    workContent += `---\n\n`;
    [...new Set(workPatterns)].forEach((item, i) => {
        workContent += `${i + 1}. ${item}\n\n`;
    });
    fs.writeFileSync(workPath, workContent, 'utf-8');
    console.log(`[+] Extracted ${[...new Set(workPatterns)].length} work patterns`);

    // Step 7: Create metadata.json
    console.log('[*] Creating metadata.json...');
    const metadata = {
        total_message_count: totalMessages,
        date_range: {
            earliest: dateRange.earliest,
            latest: dateRange.latest
        },
        main_topics: Array.from(topics).slice(0, 20),
        projects_mentioned: Array.from(projects),
        extraction_date: new Date().toISOString(),
        source_files: {
            chat_count: chatFiles.length,
            additional_docs: fs.existsSync(ADDITIONAL_DOCS) ? 'included' : 'not found'
        }
    };
    
    const metadataPath = path.join(OUTPUT_DIR, 'metadata.json');
    fs.writeFileSync(metadataPath, JSON.stringify(metadata, null, 2), 'utf-8');
    console.log(`[+] Created metadata.json`);

    // Final summary
    console.log();
    console.log('='.repeat(60));
    console.log('EXTRACTION COMPLETE');
    console.log('='.repeat(60));
    console.log();
    console.log('SUMMARY:');
    console.log(`  - Total user messages: ${totalMessages}`);
    console.log(`  - Date range: ${dateRange.earliest} to ${dateRange.latest}`);
    console.log(`  - Chat files processed: ${chatFiles.length}`);
    console.log();
    console.log('OUTPUT STRUCTURE:');
    console.log(`  ${OUTPUT_DIR}/`);
    console.log(`    ├── conversations/`);
    console.log(`    │   └── all_chats.txt (${(allChatsContent.length / 1024 / 1024).toFixed(2)} MB)`);
    console.log(`    ├── extracted/`);
    console.log(`    │   ├── constitution_raw.md (${[...new Set(constitutionRaw)].length} items)`);
    console.log(`    │   ├── doctrine_raw.md (${[...new Set(doctrineRaw)].length} items)`);
    console.log(`    │   ├── style_samples.txt (${styleSamples.length} samples)`);
    console.log(`    │   ├── theological_statements.md (${[...new Set(theologicalStatements)].length} items)`);
    console.log(`    │   ├── red_lines.md (${[...new Set(redLines)].length} items)`);
    console.log(`    │   └── work_patterns.md (${[...new Set(workPatterns)].length} items)`);
    console.log(`    └── metadata.json`);
    console.log();
    console.log('[SUCCESS] Agent identity data extracted.');
}

main().catch(err => {
    console.error('[FATAL ERROR]', err);
    process.exit(1);
});
