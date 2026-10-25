#include <vulkan/vulkan.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static constexpr int kExitSkip = 77;

static void check(VkResult result)
{
    if (result != VK_SUCCESS)
    {
        std::fprintf(stderr, "Vulkan call failed: %d\n", result);
        std::exit(1);
    }
}

int main(int argc, char** argv)
{
    // Observation drivers can record commands without executing image copies.
    const bool verify = !(argc == 2 && std::strcmp(argv[1], "--no-verify") == 0);
    if (argc != 1 && (argc != 2 || verify))
    {
        std::fprintf(stderr, "Usage: %s [--no-verify]\n", argv[0]);
        return 2;
    }
    constexpr unsigned width = 16, height = 16, data_size = width * height * 4;
    unsigned char expected[data_size];
    for (unsigned i = 0; i < data_size; ++i) expected[i] = static_cast<unsigned char>(i);
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    app.pApplicationName = "buffer memory selection";
    app.apiVersion = VK_API_VERSION_1_1;
    const char* extension = VK_EXT_DEBUG_UTILS_EXTENSION_NAME;
    VkInstanceCreateInfo instance_info{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    instance_info.pApplicationInfo = &app;
    instance_info.enabledExtensionCount = 1;
    instance_info.ppEnabledExtensionNames = &extension;
    VkInstance instance;
    check(vkCreateInstance(&instance_info, nullptr, &instance));

    uint32_t count = 0;
    check(vkEnumeratePhysicalDevices(instance, &count, nullptr));
    if (count != 1) return kExitSkip;
    VkPhysicalDevice physical;
    check(vkEnumeratePhysicalDevices(instance, &count, &physical));
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, nullptr);
    std::vector<VkQueueFamilyProperties> families(count);
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, families.data());
    uint32_t family = 0;
    while (family < count && !(families[family].queueFlags & VK_QUEUE_GRAPHICS_BIT)) ++family;
    if (family == count) return kExitSkip;

    float priority = 1.0f;
    VkDeviceQueueCreateInfo queue_info{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    queue_info.queueFamilyIndex = family;
    queue_info.queueCount = 1;
    queue_info.pQueuePriorities = &priority;
    VkDeviceCreateInfo device_info{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
    device_info.queueCreateInfoCount = 1;
    device_info.pQueueCreateInfos = &queue_info;
    VkDevice device;
    check(vkCreateDevice(physical, &device_info, nullptr, &device));
    auto set_name = reinterpret_cast<PFN_vkSetDebugUtilsObjectNameEXT>(
        vkGetDeviceProcAddr(device, "vkSetDebugUtilsObjectNameEXT"));
    if (!set_name) return kExitSkip;

    VkPhysicalDeviceMemoryProperties properties;
    vkGetPhysicalDeviceMemoryProperties(physical, &properties);
    VkFormatProperties format;
    vkGetPhysicalDeviceFormatProperties(physical, VK_FORMAT_R8G8B8A8_UNORM, &format);
    const VkFormatFeatureFlags required_format = VK_FORMAT_FEATURE_TRANSFER_SRC_BIT |
        VK_FORMAT_FEATURE_TRANSFER_DST_BIT | VK_FORMAT_FEATURE_SAMPLED_IMAGE_BIT;
    if ((format.optimalTilingFeatures & required_format) != required_format) return kExitSkip;

    VkQueue queue;
    vkGetDeviceQueue(device, family, 0, &queue);
    // upload-buffer
    VkBufferCreateInfo upload_info{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
    upload_info.size = data_size;
    upload_info.usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT;
    upload_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    VkBuffer upload_buffer;
    check(vkCreateBuffer(device, &upload_info, nullptr, &upload_buffer));
    VkDebugUtilsObjectNameInfoEXT upload_name{VK_STRUCTURE_TYPE_DEBUG_UTILS_OBJECT_NAME_INFO_EXT};
    upload_name.objectType = VK_OBJECT_TYPE_BUFFER;
    upload_name.objectHandle = reinterpret_cast<uint64_t>(upload_buffer);
    upload_name.pObjectName = "upload-buffer";
    check(set_name(device, &upload_name));
    VkMemoryRequirements upload_requirements;
    vkGetBufferMemoryRequirements(device, upload_buffer, &upload_requirements);
    VkMemoryAllocateInfo upload_allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    upload_allocation.allocationSize = upload_requirements.size;
    const VkMemoryPropertyFlags upload_required = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
    while (upload_allocation.memoryTypeIndex < properties.memoryTypeCount &&
           (!(upload_requirements.memoryTypeBits & (1u << upload_allocation.memoryTypeIndex)) ||
            (properties.memoryTypes[upload_allocation.memoryTypeIndex].propertyFlags & upload_required) != upload_required))
        ++upload_allocation.memoryTypeIndex;
    if (upload_allocation.memoryTypeIndex == properties.memoryTypeCount) return kExitSkip;
    VkDeviceMemory upload_memory;
    check(vkAllocateMemory(device, &upload_allocation, nullptr, &upload_memory));
    check(vkBindBufferMemory(device, upload_buffer, upload_memory, 0));

    // readback-buffer
    VkBufferCreateInfo readback_info{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
    readback_info.size = data_size;
    readback_info.usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    readback_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    VkBuffer readback_buffer;
    check(vkCreateBuffer(device, &readback_info, nullptr, &readback_buffer));
    VkDebugUtilsObjectNameInfoEXT readback_name{VK_STRUCTURE_TYPE_DEBUG_UTILS_OBJECT_NAME_INFO_EXT};
    readback_name.objectType = VK_OBJECT_TYPE_BUFFER;
    readback_name.objectHandle = reinterpret_cast<uint64_t>(readback_buffer);
    readback_name.pObjectName = "readback-buffer";
    check(set_name(device, &readback_name));
    VkMemoryRequirements readback_requirements;
    vkGetBufferMemoryRequirements(device, readback_buffer, &readback_requirements);
    VkMemoryAllocateInfo readback_allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    readback_allocation.allocationSize = readback_requirements.size;
    const VkMemoryPropertyFlags readback_required = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_CACHED_BIT;
    while (readback_allocation.memoryTypeIndex < properties.memoryTypeCount &&
           (!(readback_requirements.memoryTypeBits & (1u << readback_allocation.memoryTypeIndex)) ||
            (properties.memoryTypes[readback_allocation.memoryTypeIndex].propertyFlags & readback_required) != readback_required))
        ++readback_allocation.memoryTypeIndex;
    if (readback_allocation.memoryTypeIndex == properties.memoryTypeCount) return kExitSkip;
    VkDeviceMemory readback_memory;
    check(vkAllocateMemory(device, &readback_allocation, nullptr, &readback_memory));
    check(vkBindBufferMemory(device, readback_buffer, readback_memory, 0));

    // optimal-image
    VkImageCreateInfo image_info{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
    image_info.imageType = VK_IMAGE_TYPE_2D;
    image_info.format = VK_FORMAT_R8G8B8A8_UNORM;
    image_info.extent = {width, height, 1};
    image_info.mipLevels = image_info.arrayLayers = 1;
    image_info.samples = VK_SAMPLE_COUNT_1_BIT;
    image_info.tiling = VK_IMAGE_TILING_OPTIMAL;
    image_info.usage = VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
    image_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    VkImage image;
    check(vkCreateImage(device, &image_info, nullptr, &image));
    VkDebugUtilsObjectNameInfoEXT image_name{VK_STRUCTURE_TYPE_DEBUG_UTILS_OBJECT_NAME_INFO_EXT};
    image_name.objectType = VK_OBJECT_TYPE_IMAGE;
    image_name.objectHandle = reinterpret_cast<uint64_t>(image);
    image_name.pObjectName = "optimal-image";
    check(set_name(device, &image_name));
    VkMemoryRequirements image_requirements;
    vkGetImageMemoryRequirements(device, image, &image_requirements);
    VkMemoryAllocateInfo image_allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    image_allocation.allocationSize = image_requirements.size;
    const VkMemoryPropertyFlags image_required = VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT;
    while (image_allocation.memoryTypeIndex < properties.memoryTypeCount &&
           (!(image_requirements.memoryTypeBits & (1u << image_allocation.memoryTypeIndex)) ||
            (properties.memoryTypes[image_allocation.memoryTypeIndex].propertyFlags & image_required) != image_required))
        ++image_allocation.memoryTypeIndex;
    if (image_allocation.memoryTypeIndex == properties.memoryTypeCount) return kExitSkip;
    VkDeviceMemory image_memory;
    check(vkAllocateMemory(device, &image_allocation, nullptr, &image_memory));
    check(vkBindImageMemory(device, image, image_memory, 0));

    void* mapped;
    check(vkMapMemory(device, upload_memory, 0, VK_WHOLE_SIZE, 0, &mapped));
    std::memcpy(mapped, expected, data_size);
    // Upload memory is HOST_COHERENT; capture intentionally has no explicit flush.
    vkUnmapMemory(device, upload_memory);

    VkCommandPoolCreateInfo pool_info{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    pool_info.queueFamilyIndex = family;
    VkCommandPool pool;
    check(vkCreateCommandPool(device, &pool_info, nullptr, &pool));
    VkCommandBufferAllocateInfo command_info{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    command_info.commandPool = pool;
    command_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    command_info.commandBufferCount = 1;
    VkCommandBuffer command;
    check(vkAllocateCommandBuffers(device, &command_info, &command));
    VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    check(vkBeginCommandBuffer(command, &begin));

    // Submission makes the coherent CPU upload available to the transfer.
    VkImageMemoryBarrier image_barrier{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
    image_barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    image_barrier.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    image_barrier.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    image_barrier.srcQueueFamilyIndex = image_barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    image_barrier.image = image;
    image_barrier.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
    vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                         0, 0, nullptr, 0, nullptr, 1, &image_barrier);
    VkBufferImageCopy copy{};
    copy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
    copy.imageExtent = {width, height, 1};
    vkCmdCopyBufferToImage(command, upload_buffer, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);

    image_barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    image_barrier.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    image_barrier.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    image_barrier.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                         0, 0, nullptr, 0, nullptr, 1, &image_barrier);
    vkCmdCopyImageToBuffer(command, image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, readback_buffer, 1, &copy);

    VkBufferMemoryBarrier host_barrier{VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER};
    host_barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    host_barrier.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
    host_barrier.srcQueueFamilyIndex = host_barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    host_barrier.buffer = readback_buffer;
    host_barrier.size = VK_WHOLE_SIZE;
    vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT,
                         0, 0, nullptr, 1, &host_barrier, 0, nullptr);
    check(vkEndCommandBuffer(command));
    VkFenceCreateInfo fence_info{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    VkFence fence;
    check(vkCreateFence(device, &fence_info, nullptr, &fence));
    VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};
    submit.commandBufferCount = 1;
    submit.pCommandBuffers = &command;
    check(vkQueueSubmit(queue, 1, &submit, fence));
    check(vkWaitForFences(device, 1, &fence, VK_TRUE, UINT64_MAX));

    check(vkMapMemory(device, readback_memory, 0, VK_WHOLE_SIZE, 0, &mapped));
    // Map and invalidate the whole allocation to satisfy noncoherent atom alignment.
    VkMappedMemoryRange range{VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE};
    range.memory = readback_memory;
    range.size = VK_WHOLE_SIZE;
    check(vkInvalidateMappedMemoryRanges(device, 1, &range));
    // Read every byte even on an observation driver; only comparison is optional.
    const volatile unsigned char* readback = static_cast<unsigned char*>(mapped);
    unsigned mismatches = 0;
    unsigned checksum = 0;
    for (unsigned i = 0; i < data_size; ++i)
    {
        const unsigned char value = readback[i];
        checksum += value;
        mismatches += value != expected[i];
    }
    vkUnmapMemory(device, readback_memory);
    std::printf("Read %u bytes from GPU transfer destination; checksum=%u; %s\n",
                data_size, checksum, verify ? (mismatches ? "verification FAILED" : "verification PASSED") :
                "data comparison disabled (observation-only run)");

    vkDestroyFence(device, fence, nullptr);
    vkDestroyCommandPool(device, pool, nullptr);
    vkDestroyImage(device, image, nullptr);
    vkDestroyBuffer(device, upload_buffer, nullptr);
    vkDestroyBuffer(device, readback_buffer, nullptr);
    vkFreeMemory(device, upload_memory, nullptr);
    vkFreeMemory(device, readback_memory, nullptr);
    vkFreeMemory(device, image_memory, nullptr);
    vkDestroyDevice(device, nullptr);
    vkDestroyInstance(instance, nullptr);
    return verify && mismatches ? 1 : 0;
}
