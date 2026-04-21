import { prisma } from "./prisma";

// 单用户模式下的默认账户 ID（无需登录系统）
const DEFAULT_ACCOUNT_ID = "default-user";

/**
 * 获取或创建默认用户
 * 开发/演示阶段使用单用户模式，无需认证
 */
export async function getOrCreateDefaultUser() {
  return prisma.user.upsert({
    where: { accountId: DEFAULT_ACCOUNT_ID },
    update: {},
    create: {
      accountId: DEFAULT_ACCOUNT_ID,
      profile: JSON.stringify({ name: "默认用户" }),
      preferences: "{}",
    },
  });
}
