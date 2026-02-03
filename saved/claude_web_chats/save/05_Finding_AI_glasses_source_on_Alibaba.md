# Finding AI glasses source on Alibaba

**UUID:** 685ad579-04b1-4bf7-be81-c63962330b03
**Created:** 2025-12-06T22:11:10.471437Z
**Updated:** 2026-02-01T00:14:30.209156Z

---

## USER

when searching for these ai glaseeseon 16888 i cant find them butt hereoinn ali baba i know baba is the middle man so how can find the source,

## ASSISTANT

 I can see those are smart glasses with a fairly standard rectangular frame design. Finding the original manufacturer on 1688 (China's domestic wholesale platform, as opposed to Alibaba which targets international buyers) can be tricky, but here's how to approach it:

**Practical steps to find the source factory:**

1. **Reverse image search on 1688.com directly** — 1688 has a built-in image search feature. Download a clean product image and upload it there. This often reveals the actual OEM/ODM manufacturer.

2. **Search in Chinese** — Try terms like:
   - 智能眼镜 (smart glasses)
   - AI眼镜 (AI glasses)
   - 蓝牙眼镜 (Bluetooth glasses)
   - 录像眼镜 (recording glasses)

3. **Look for factory indicators on 1688 listings** — Factories often have badges like "实力工厂" (verified factory) or "源头工厂" (source factory). These are more likely to be actual manufacturers rather than trading companies.

4. **Check the MOQ** — Real factories typically have higher minimum orders (100-500+ units). If MOQ is 1-2 pieces, it's probably a reseller.

5. **Ask the Alibaba seller directly** — Some will tell you the factory name or even their 1688 store if you're serious about bulk orders.

**Alternative approach:**
If you find a listing on 1688, look at the company name and search that separately — many factories have both a 1688 store (domestic) and Alibaba store (export), but the 1688 prices are typically 30-50% lower.

Want me to search for any specific features these glasses have to help narrow it down?

## USER

or betetr yet hoow can i acutlal bild it from scratch my way ,

## ASSISTANT

 That's the move — building your own gives you full control over specs, aesthetics, and margins. Here's how to approach it:

**Core components you'd need:**

1. **Frames** — Source blank frames from eyewear manufacturers on 1688. Search "眼镜框架" or "TR90眼镜" (TR90 is a common flexible material). You can also get custom molds made, but that's $2-5k+ upfront.

2. **Main board/chip** — Common options:
   - ESP32 — cheap, has Bluetooth/WiFi, lots of documentation, good for basic smart glasses
   - Qualcomm QCC3040/5141 — better for audio-focused glasses
   - For actual AI processing, you'd likely offload to a phone app via Bluetooth

3. **Camera module** — Small FPC cameras (look for "微型摄像头模组"), typically 2-8MP. OV2640 or OV5640 sensors are common and cheap.

4. **Audio** — Bone conduction transducers or small directional speakers that sit near the temple. Search "骨传导喇叭"

5. **Battery** — Small LiPo cells that fit in the temples. You're looking at maybe 100-200mAh per side realistically.

6. **Microphone** — MEMS mics are tiny and work well

**Two paths forward:**

**Path A — Modify existing hardware**
Buy cheap open-frame smart glasses, gut them, and rebuild into your own frame design. Faster to prototype.

**Path B — Ground-up build**
Source each component, find a PCB designer (or learn KiCad), and work with a Shenzhen assembly house.

**Realistic first step:**
Get an ESP32 dev board, a small camera module, and a Bluetooth audio setup. Prototype the functionality before worrying about fitting it into frames.

What's your vision for what these glasses would actually *do*? That'll determine which components matter most.

