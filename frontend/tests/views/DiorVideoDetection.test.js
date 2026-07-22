import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const apiSource = readFileSync(resolve(process.cwd(), 'src/api/detection.js'), 'utf8')
const facilityPageSource = readFileSync(resolve(process.cwd(), 'src/views/FacilityDetectionPage.vue'), 'utf8')
const chatPageSource = readFileSync(resolve(process.cwd(), 'src/views/ChatPage.vue'), 'utf8')

describe('DIOR 视频检测入口', () => {
  it('调用独立的 DIOR 视频端点', () => {
    expect(apiSource).toContain("export const detectVideo")
    expect(apiSource).toContain("'/detection/video'")
  })

  it('在 DIOR 页面支持视频采样配置和结果展示', () => {
    expect(facilityPageSource).toContain("value=\"video\"")
    expect(facilityPageSource).toContain("frame_sample_rate")
    expect(facilityPageSource).toContain("max_frames")
    expect(facilityPageSource).toContain("await detectVideo(form)")
  })

  it('聊天快捷入口将结果交给 DIOR 结果卡', () => {
    expect(chatPageSource).toContain("handleQuickSegment('dior-video')")
    expect(chatPageSource).toContain('await detectDiorVideo(formData)')
    expect(chatPageSource).toContain('lastMsg.facilityDetectionResult = result')
  })

  it('摄像头拍照、采样和实时模式都可以切换到 DIOR', () => {
    expect(chatPageSource).toContain('v-model="cameraModel"')
    expect(chatPageSource).toContain('DIOR 设施检测')
    expect(chatPageSource).toContain('await detectDiorSingle(formData)')
    expect(chatPageSource).toContain('await detectDiorBatch(formData)')
    expect(chatPageSource).toContain("detect_dior_camera_realtime")
  })

  it('普通消息附件支持单个视频并按消息意图选择模型', () => {
    expect(chatPageSource).toContain('accept="image/*,video/*')
    expect(chatPageSource).toContain('async function sendSelectedVideo')
    expect(chatPageSource).toContain('requestedVideoModels(message)')
    expect(chatPageSource).toContain('msg.videoPreview')
    expect(chatPageSource).toContain("return ['loveda', 'dior']")
  })
})
